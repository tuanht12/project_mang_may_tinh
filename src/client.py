"""\
Đây là file chính cho phía máy khách (client) của ứng dụng chat.
Trách nhiệm của nó bao gồm:
- Tạo kết nối đến server.
- Cung cấp giao diện dòng lệnh (CLI) cho người dùng.
- Xử lý quá trình xác thực (Đăng nhập/Đăng ký).
- Bắt đầu phiên chat, sử dụng 2 luồng:
    1. Luồng chính (Main Thread) để gửi tin nhắn (chờ input).
    2. Luồng nhận (Receive Thread) để nhận tin nhắn (chờ recv).
- Xử lý việc mất kết nối và tự động kết nối lại (reconnect).
"""

import time
from schemas import (
    AuthAction,
    AuthRequest,
    ChatMessage,
    GenericMessage,
    MessageType,
    ServerResponse,
    ServerResponseType,
)
import socket
import threading
from configs import DEFAULT_BUFFER_SIZE, SERVER_HOST, SERVER_PORT, QUIT_COMMAND
from utils import close_socket, get_user_credentials, request_user_login_register
from queue import Queue

MAX_RECONNECTION_ATTEMPTS = 3
SLEEP_BETWEEN_RETRIES = 2  # seconds


def attempt_reconnection(client_credentials):
    """
    Cố gắng kết nối lại với máy chủ sau khi bị mất kết nối.
    Hàm này sẽ thử kết nối lại và tự động đăng nhập lại.

    Args:
        client_credentials (dict): Thông tin đăng nhập (username, password)
                                   của người dùng.

    Returns:
        socket.socket: Một đối tượng socket mới đã kết nối và xác thực thành công.
        None: Nếu không thể kết nối lại sau tất cả các lần thử.
    """
    for attempt in range(1, MAX_RECONNECTION_ATTEMPTS + 1):
        print(f"Reconnection attempt {attempt}/{MAX_RECONNECTION_ATTEMPTS}")
        # Tăng thời gian chờ giữa các lần thử
        sleep_time = SLEEP_BETWEEN_RETRIES**attempt
        # 1. Thử tạo kết nối mới
        new_socket = create_connection()
        if new_socket is None:
            time.sleep(sleep_time)
            continue
        # 2. Thử xác thực lại
        is_passed, _ = authenticate_with_server(
            new_socket, AuthAction.LOGIN, client_credentials
        )
        if is_passed:
            print("Reconnected successfully!")
            return new_socket
        else:
            close_socket(new_socket)
            time.sleep(sleep_time)

    print("Failed to reconnect after all attempts")
    return None


def receive_messages(
    client_socket: socket.socket,
    stop_event: threading.Event,
    reconnect_event: threading.Event,
):
    """
    Hàm chạy trong một luồng riêng, chuyên để lắng nghe
    và nhận tin nhắn từ server.

    Args:
        client_socket (socket.socket): Socket đang kết nối.
        stop_event (threading.Event): Cờ hiệu để dừng luồng (khi người dùng /quit).
        reconnect_event (threading.Event): Cờ hiệu báo cần kết nối lại.
    """
    should_reconnect = False
    while not stop_event.is_set():
        try:
            # Receive message from the server
            generic_message_bytes = client_socket.recv(DEFAULT_BUFFER_SIZE)
            # If no data is received, the server has closed the connection
            if not generic_message_bytes:
                should_reconnect = True
                break
            generic_msg = GenericMessage.model_validate_json(generic_message_bytes)
            if generic_msg.type == MessageType.CHAT:
                chat_msg = ChatMessage.model_validate(generic_msg.payload)
                print(chat_msg.message_string)
            elif generic_msg.type == MessageType.RESPONSE:
                server_resp = ServerResponse.model_validate(generic_msg.payload)
                print(server_resp.message_str)
        except ConnectionResetError:
            print("Connection to the server was lost.")
            should_reconnect = True
            break
        except Exception:
            break
    # --- Dọn dẹp luồng nhận ---
    # Nếu cần kết nối lại, kích hoạt cờ hiệu
    if should_reconnect and not reconnect_event.is_set():
        reconnect_event.set()
    # Luôn kích hoạt cờ stop để báo cho luồng gửi dừng lại
    if not stop_event.is_set():
        stop_event.set()


def send_message_text(message_text: str, client_socket: socket.socket, nickname: str):
    """
    Đóng gói và gửi một tin nhắn văn bản đến server.

    Args:
        message_text (str): Nội dung tin nhắn thô từ người dùng.
        client_socket (socket.socket): Socket đang kết nối.
        nickname (str): Tên người dùng hiện tại.
    """
    if message_text:
        # Tạo và đóng gói tin nhắn chat

        chat_msg = ChatMessage(
            sender=nickname, content=message_text, timestamp=int(time.time())
        )
        # Đóng gói tin nhắn chat vào GenericMessage
        generic_msg = GenericMessage(
            type=MessageType.CHAT, payload=chat_msg.model_dump()
        )
        # Gửi tin nhắn đã đóng gói đến server
        client_socket.send(generic_msg.encoded_bytes)


def send_messages(
    client_socket: socket.socket,
    nickname: str,
    stop_event: threading.Event,
    reconnect_event: threading.Event,
    message_buffer: Queue,
):
    """
    Hàm chạy trong luồng chính, chuyên để lấy input từ người dùng
    và gửi tin nhắn đi.

    Args:
        client_socket (socket.socket): Socket đang kết nối.
        nickname (str): Tên người dùng.
        stop_event (threading.Event): Cờ hiệu để dừng luồng.
        reconnect_event (threading.Event): Cờ hiệu báo cần kết nối lại.
        message_buffer (Queue): Hàng đợi để lưu tin nhắn khi mất kết nối.
    """
    should_reconnect = False
    while not stop_event.is_set():
        try:
            # --- Gửi tin nhắn trong bộ đệm (nếu có) ---
            # (Xảy ra sau khi kết nối lại thành công)
            while not message_buffer.empty():
                message_text = message_buffer.get()
                send_message_text(message_text, client_socket, nickname)
            # --- Nhận input từ người dùng ---
            message_text = input("> ")

            # Kiểm tra lệnh thoát
            if message_text.strip() == QUIT_COMMAND:
                print("Exiting chat...")
                break
            # Nếu luồng nhận phát hiện mất kết nối
            if reconnect_event.is_set():
                message_buffer.put(message_text)
                break
            send_message_text(message_text, client_socket, nickname)
        except (EOFError, KeyboardInterrupt):
            print("\nDisconnecting...")
            break
        except (ConnectionResetError, BrokenPipeError):
            print("Connection lost during send")
            should_reconnect = True
            break
        except Exception as e:
            print(f"Failed to send message. Connection might be closed. Error: {e}")
            break
    # --- Dọn dẹp luồng gửi ---
    if should_reconnect and not reconnect_event.is_set():
        reconnect_event.set()
    if not stop_event.is_set():
        stop_event.set()


def create_connection() -> socket.socket:
    """
    Tạo và thiết lập một kết nối socket mới đến server.

    Returns:
        socket.socket: Socket đã kết nối, hoặc None nếu thất bại.
    """
    try:
        client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client_socket.connect((SERVER_HOST, SERVER_PORT))
        return client_socket
    except KeyboardInterrupt:
        print("\nClient exiting...")
        return None
    except ConnectionRefusedError:
        print("Connection failed. Is the server running?")
        return None
    except Exception as e:
        print(f"Failed to create connection: {e}")
        return None


def authenticate_with_server(
    client_socket: socket.socket, action: AuthAction, client_credentials: dict
) -> tuple[bool, socket.socket]:
    """
    Gửi yêu cầu xác thực (Đăng nhập/Đăng ký) đến server.
    Hàm này có logic tự động thử lại nếu kết nối bị gián đoạn.

    Args:
        client_socket (socket.socket): Socket để gửi yêu cầu.
        action (AuthAction): Hành động (LOGIN hoặc REGISTER).
        client_credentials (dict): Chứa 'username' và 'password'.

    Returns:
        tuple[bool, socket.socket]: (Thành công, socket đã dùng)
             - (True, socket) nếu đăng nhập thành công.
             - (False, socket) nếu thất bại nhưng socket vẫn ổn.
             - (False, None) nếu thất bại và không thể kết nối lại.
    """
    current_socket = client_socket
    # Tạo yêu cầu xác thực
    auth_req = AuthRequest(
        action=action,
        username=client_credentials["username"],
        password=client_credentials["password"],
    )
    auth_msg = GenericMessage(type=MessageType.AUTH, payload=auth_req.model_dump())
    # Vòng lặp thử lại (dùng cho trường hợp mất kết nối khi đang xác thực)
    for attempt in range(1, MAX_RECONNECTION_ATTEMPTS + 1):
        try:
            current_socket.send(auth_msg.encoded_bytes)
            response_bytes = current_socket.recv(DEFAULT_BUFFER_SIZE)
            if not response_bytes:
                print("Server disconnected during authentication.")
                raise ConnectionResetError("Server disconnected")
        except (ConnectionResetError, BrokenPipeError, OSError):
            close_socket(current_socket)
            if attempt == MAX_RECONNECTION_ATTEMPTS:
                print("Failed to authenticate after all reconnection attempts")
                return False, None
            sleep_time = SLEEP_BETWEEN_RETRIES**attempt
            print(
                f"Attempt {attempt}/{MAX_RECONNECTION_ATTEMPTS} "
                f"in {sleep_time} seconds..."
            )
            time.sleep(sleep_time)
            new_socket = create_connection()
            if new_socket is None:
                print(f"Failed to reconnect for authentication attempt {attempt}")
                continue
            else:
                print("Reconnected successfully")
                current_socket = new_socket
                continue
        except Exception as e:
            print(f"Error processing authentication response: {e}")
            return False, None
        break  # Exit loop if no exception occurred

    resp_generic = GenericMessage.model_validate_json(response_bytes)
    if resp_generic.type == MessageType.RESPONSE:
        server_resp = ServerResponse.model_validate(resp_generic.payload)
        print(server_resp.message_str)

        success = (
            server_resp.status == ServerResponseType.SUCCESS
            and action == AuthAction.LOGIN
        )
        return success, current_socket

    return False, current_socket


def perform_authentication(
    client_socket: socket.socket, client_credentials: dict
) -> tuple[str, socket.socket]:
    """
    Xử lý toàn bộ quy trình xác thực người dùng (menu, nhập liệu,
    gửi yêu cầu, nhận phản hồi).

    Args:
        client_socket (socket.socket): Socket ban đầu.
        client_credentials (dict): Một dict rỗng để lưu trữ thông tin.

    Returns:
        tuple[str, socket.socket]: (username, socket) nếu thành công,
                                   (None, socket) nếu thất bại.
    """
    current_socket = client_socket

    while True:
        try:
            # 1. Hiển thị menu (Đăng nhập / Đăng ký)
            action = request_user_login_register()
            if action is None:
                return None, current_socket

            # 2. Lấy thông tin (username / password)
            username, password = get_user_credentials()
            if username is None or password is None:
                continue

            # Lưu thông tin xác thực đêng sử dụng sau này
            client_credentials["username"] = username
            client_credentials["password"] = password

            # 3. Gửi yêu cầu xác thực đến server
            success, new_socket = authenticate_with_server(
                current_socket, action, client_credentials
            )

            if new_socket is None:
                # Authentication failed due to connection issues
                return None, None

            current_socket = new_socket  # Update socket in case it was reconnected

            if success and action == AuthAction.LOGIN:
                return username, current_socket
            else:
                # Authentication failed, but socket is still valid - continue trying
                continue

        except KeyboardInterrupt:
            print("\nExiting authentication...")
            return None, current_socket


def start_chat_session(client_socket: socket.socket, client_credentials: dict):
    """
    Bắt đầu phiên chat chính.
    Quản lý vòng lặp chạy 2 luồng (gửi/nhận) và xử lý
    logic tự động kết nối lại.

    Args:
        client_socket (socket.socket): Socket đã được xác thực.
        client_credentials (dict): Thông tin của người dùng.
    """
    message_buffer = Queue()  # Hàng đợi lưu tin nhắn khi mất kết nối

    # Vòng lặp chính của phiên chat
    # Vòng lặp này sẽ lặp lại mỗi khi thực hiện kết nối lại
    while True:
        stop_event = threading.Event()
        reconnect_event = threading.Event()
        # --- Bắt đầu luồng nhận ---
        receive_thread = threading.Thread(
            target=receive_messages, args=(client_socket, stop_event, reconnect_event)
        )
        receive_thread.daemon = True
        receive_thread.start()

        # --- Bắt đầu luồng gửi (chạy trên luồng chính) ---
        send_messages(
            client_socket,
            client_credentials["username"],
            stop_event,
            reconnect_event,
            message_buffer,
        )
        # User wants to quit
        if stop_event.is_set() and not reconnect_event.is_set():
            print("Chat session ended.")
            break
        elif reconnect_event.is_set():
            print("Attempting to reconnect...")
            close_socket(client_socket)
            client_socket = attempt_reconnection(client_credentials)
            if client_socket is None:
                print("Could not reconnect. Exiting chat session.")
                break
            else:
                print("Reconnected. You can continue chatting.")
                continue
        else:
            break


def run():
    """
    Hàm `run` chính của client.
    Điều phối toàn bộ quá trình: Kết nối, Xác thực, Chat.
    """
    # 1. Tạo kết nối ban đầu
    client_socket = create_connection()
    if client_socket is None:
        return
    client_credentials = {"username": None, "password": None}
    try:
        # 2. Thực hiện xác thực
        username, client_socket = perform_authentication(
            client_socket, client_credentials
        )
        if username is None or client_socket is None:
            print("Exiting...")
            return

        # 3. Bắt đầu phiên chat
        start_chat_session(client_socket, client_credentials)
    finally:
        # --- Dọn dẹp cuối cùng ---
        # Đảm bảo socket luôn được đóng khi chương trình kết thúc
        if client_socket:
            close_socket(client_socket)


if __name__ == "__main__":
    run()
