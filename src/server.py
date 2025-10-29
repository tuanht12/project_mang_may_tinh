"""\
Đây là file chính cho phía máy chủ của ứng dụng chat.
Trách nhiệm của nó bao gồm:
- Khởi tạo và lắng nghe các kết nối socket đến.
- Chấp nhận các client mới.
- Xử lý mỗi client trong một luồng (thread) riêng biệt.
- Điều phối các giai đoạn: Xác thực (auth) và Trò chuyện (chat).
- Quản lý trạng thái chung, bao gồm danh sách client và khóa (lock).
- Đọc và ghi vào file CSV chứa dữ liệu người dùng.
"""

import json
from typing import List

from pydantic import ValidationError
from chat_client import ChatClient
from configs import (
    DB_PATH,
    DEFAULT_BUFFER_SIZE,
    SERVER_PORT,
    SERVER_HOST,
    USERS_CSV,
    get_welcome_message,
)
import socket
import threading
from schemas import (
    AuthAction,
    AuthRequest,
    ChatMessage,
    GenericMessage,
    MessageType,
    ServerResponse,
    ServerResponseType,
)
from utils import add_new_user_to_db, verify_user_credentials, close_socket
import pandas as pd
import os

# --- State ---
# List to keep track of all connected client sockets
clients: List[ChatClient] = []
# Lock to ensure that the clients list is accessed by only one thread at a time
clients_lock = threading.Lock()
csv_lock = threading.Lock()  # Lock for accessing the CSV file


def load_users_df():
    """
    Tải file CSV chứa thông tin người dùng vào một pandas DataFrame.
    Nếu file không tồn tại, hàm sẽ tạo file và thư mục cần thiết.

    Returns:
        pd.DataFrame: DataFrame chứa dữ liệu người dùng.
    """
    # Sử dụng khóa để đảm bảo chỉ một luồng được phép truy cập file CSV
    # (ngăn chặn 2 luồng cùng đọc/ghi file một lúc)
    with csv_lock:
        if not os.path.exists(USERS_CSV):
            os.makedirs(DB_PATH, exist_ok=True)
            df = pd.DataFrame(columns=["username", "password"])
            df.to_csv(USERS_CSV, index=False)
            return df
        return pd.read_csv(USERS_CSV)


def save_users_df(df: pd.DataFrame):
    """Lưu DataFrame trở lại file CSV."""
    # Sử dụng khóa để đảm bảo chỉ một luồng được phép truy cập file CSV
    with csv_lock:
        df.to_csv(USERS_CSV, index=False)


def create_server_socket():
    """
    Tạo, cấu hình và trả về một socket server đang lắng nghe.
    Socket được thiết lập để lắng nghe trên SERVER_HOST và SERVER_PORT.

    Returns:
        socket.socket: Đối tượng socket của server đã được bind và listen.
    """
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    # Cấu hình socket để cho phép tái sử dụng địa chỉ ngay lập tức
    # (hữu ích khi khởi động lại server nhanh)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    # Gắn socket vào địa chỉ và cổng đã định
    server_socket.bind((SERVER_HOST, SERVER_PORT))
    # Bắt đầu lắng nghe kết nối đến
    server_socket.listen()
    print(f"[INFO] Server đang lắng nghe trên {SERVER_HOST}:{SERVER_PORT}")
    return server_socket


def send_generic_message_bytes(generic_msg_bytes: bytes, client: ChatClient):
    """
    Gửi một tin nhắn (đã ở dạng bytes) đến một client cụ thể.
    Xử lý lỗi nếu gửi thất bại và loại bỏ client nếu cần.

    Args:
        generic_msg_bytes (bytes): Dữ liệu tin nhắn đã được mã hóa.
        client (ChatClient): Đối tượng client người nhận.
    """
    try:
        client.socket.send(generic_msg_bytes)
    except Exception as e:
        # Xử lý lỗi gửi tin nhắn
        print(f"Failed to send message to {client.username}. Error: {e}")
        # Loại bỏ client khỏi danh sách nếu không thể gửi tin nhắn
        close_socket(client.socket)
        # Loại bỏ client khỏi danh sách clients
        with clients_lock:
            if client in clients:
                clients.remove(client)


def broadcast(message_bytes: bytes, sending_client: ChatClient):
    """
    Gửi một tin nhắn (dạng bytes) đến TẤT CẢ các client đang hoạt động,
    TRỪ client đã gửi tin nhắn đó.

    Args:
        message_bytes (bytes): Dữ liệu tin nhắn cần gửi.
        sending_client (ChatClient): Client gốc đã gửi tin nhắn.
    """
    # Sử dụng khóa để đảm bảo truy cập an toàn vào danh sách clients
    with clients_lock:
        for client in clients:
            if client != sending_client:
                send_generic_message_bytes(message_bytes, client)


def handle_private_message(chat_message: ChatMessage, sending_client: ChatClient):
    """
    Xử lý một tin nhắn riêng tư (bắt đầu bằng /pm).
    Tìm người nhận và chỉ gửi tin nhắn cho họ.

    Args:
        chat_message (ChatMessage): Đối tượng tin nhắn chat đã được phân tích.
        sending_client (ChatClient): Client đã gửi tin nhắn riêng.
    """
    _, recipient, content = chat_message.content.split(" ", 2)
    with clients_lock:
        recipient_client = next((c for c in clients if c.username == recipient), None)
        if recipient_client:
            private_msg = ChatMessage(
                sender=chat_message.sender,
                content=f"(private) {content}",
                timestamp=chat_message.timestamp,
            )
            private_generic_msg = GenericMessage(
                type=MessageType.CHAT, payload=private_msg.model_dump()
            )
            if recipient_client != sending_client:
                send_generic_message_bytes(
                    private_generic_msg.encoded_bytes, recipient_client
                )
        else:
            # Gửi phản hồi lỗi trở lại client gửi tin nhắn
            error_response = ServerResponse(
                status=ServerResponseType.ERROR,
                content=f"User '{recipient}' not found or not online.",
            )
            error_generic_msg = GenericMessage(
                type=MessageType.RESPONSE, payload=error_response.model_dump()
            )
            send_generic_message_bytes(error_generic_msg.encoded_bytes, sending_client)


def handle_get_active_users(sending_client: ChatClient) -> None:
    """
    Xử lý lệnh /users (hoặc SHOW_USERS_COMMAND).
    Lấy danh sách username và gửi lại cho client yêu cầu.

    Args:
        sending_client (ChatClient): Client đã gõ lệnh /users.
    """
    with clients_lock:
        active_usernames = [client.username for client in clients if client.username]
    users_list = "\n".join(active_usernames) if active_usernames else "No users online."
    server_response = ServerResponse(
        status=ServerResponseType.SUCCESS,
        content=f"Active users:\n{users_list}",
    )
    server_response_msg = GenericMessage(
        type=MessageType.RESPONSE, payload=server_response.model_dump()
    )
    # Gửi danh sách người dùng trở lại client yêu cầu
    send_generic_message_bytes(server_response_msg.encoded_bytes, sending_client)


def handle_chat_message(
    generic_msg: GenericMessage, sending_client: ChatClient
) -> None:
    """
    Phân tích và xử lý một tin nhắn CHAT đến.
    Hàm này quyết định tin nhắn là riêng tư, lệnh, hay công khai.

    Args:
        generic_msg (GenericMessage): Đối tượng tin nhắn chung.
        sending_client (ChatClient): Client đã gửi tin nhắn.
    """
    chat_message = ChatMessage.model_validate(generic_msg.payload)
    print(chat_message.message_string)
    # Xử lý tin nhắn dựa trên loại
    if chat_message.is_private:
        # Tin nhắn riêng tư
        handle_private_message(chat_message, sending_client)
    elif chat_message.content.strip() == "/users":
        # Lệnh hiển thị người dùng đang hoạt động
        handle_get_active_users(sending_client)
    else:
        # Tin nhắn công khai - phát sóng đến tất cả client khác
        broadcast(generic_msg.encoded_bytes, sending_client)


def handle_chat(client: ChatClient):
    """
    Vòng lặp chính xử lý các tin nhắn CHAT từ một client
    (sau khi đã xác thực thành công).

    Args:
        client (ChatClient): Client đang trong phiên chat.
    """
    while True:
        try:
            # Chờ nhận tin nhắn từ client
            generic_message_bytes = client.socket.recv(DEFAULT_BUFFER_SIZE)

            # Nếu nhận được bytes rỗng, client đã đóng kết nối
            if not generic_message_bytes:
                print(f"Finished handling chat {client.peer_name}.")
                break

            generic_msg = GenericMessage.model_validate_json(generic_message_bytes)
            if generic_msg.type == MessageType.CHAT:
                handle_chat_message(generic_msg, client)

        except ConnectionResetError:
            # Handle the case where the client forcefully closes the connection
            print(f"{client.peer_name} disconnected unexpectedly.")
            break
        except Exception as e:
            print(f"[ERROR] {e}")
            break

    # Khi vòng lặp kết thúc, thông báo rằng người dùng đã offline
    notice_user_presence(client.username, online=False)


def is_username_active(username: str) -> bool:
    """
    Kiểm tra xem username đã được sử dụng bởi một client
    đang hoạt động (đã đăng nhập) hay chưa.

    Args:
        username (str): Tên người dùng cần kiểm tra.

    Returns:
        bool: True nếu username đã được sử dụng, False nếu chưa.
    """
    with clients_lock:
        return any(client.username == username for client in clients)


def notice_user_presence(username: str, online: bool):
    """
    Thông báo cho tất cả các client khác về sự thay đổi trạng thái
    (online/offline) của một người dùng.

    Args:
        username (str): Tên người dùng đã thay đổi trạng thái.
        online (bool): True nếu vừa online, False nếu vừa offline.
    """
    status = "online" if online else "offline"
    notification = ServerResponse(
        status=ServerResponseType.INFO,
        content=f"User '{username}' is now {status}.",
    )
    notification_msg = GenericMessage(
        type=MessageType.RESPONSE, payload=notification.model_dump()
    )
    with clients_lock:
        for client in clients:
            if client.username != username:
                send_generic_message_bytes(notification_msg.encoded_bytes, client)


def handle_auth(client: ChatClient):
    """
    Xử lý pha xác thực (Đăng nhập/Đăng ký) cho một client mới.
    Vòng lặp này chạy cho đến khi client xác thực thành công hoặc
    ngắt kết nối.

    Args:
        client (ChatClient): Client mới kết nối, chưa xác thực.

    Returns:
        str: Tên người dùng (username) nếu xác thực thành công.
        None: Nếu client ngắt kết nối trước khi xác thực.
    """
    username = None
    while True:
        # Chờ nhận yêu cầu xác thực từ client
        auth_bytes = client.socket.recv(DEFAULT_BUFFER_SIZE)
        if not auth_bytes:
            return  # Client đã ngắt kết nối

        try:
            generic_msg = GenericMessage.model_validate_json(auth_bytes)
            if generic_msg.type != MessageType.AUTH:
                continue  # Bỏ qua nếu không phải tin nhắn AUTH

            auth_req = AuthRequest.model_validate(generic_msg.payload)
            users_df = load_users_df()

            # Xử lý yêu cầu đăng ký
            if auth_req.action == AuthAction.REGISTER:
                # Kiểm tra nếu username đã tồn tại
                if auth_req.username in users_df["username"].values:
                    response = ServerResponse(
                        status=ServerResponseType.ERROR,
                        content="Username already exists.",
                    )
                else:
                    users_df = add_new_user_to_db(
                        users_df, auth_req.username, auth_req.password
                    )
                    save_users_df(users_df)
                    response = ServerResponse(
                        status=ServerResponseType.SUCCESS,
                        content="Registration successful. Please log in.",
                    )
            # Xử lý yêu cầu đăng nhập
            elif auth_req.action == AuthAction.LOGIN:
                if verify_user_credentials(
                    users_df, auth_req.username, auth_req.password
                ) and not is_username_active(auth_req.username):
                    response = ServerResponse(
                        status=ServerResponseType.SUCCESS,
                        content=get_welcome_message(auth_req.username),
                    )
                    username = auth_req.username
                elif is_username_active(auth_req.username):
                    response = ServerResponse(
                        status=ServerResponseType.ERROR,
                        content="This user is already logged in.",
                    )
                else:
                    response = ServerResponse(
                        status=ServerResponseType.ERROR,
                        content="Invalid username or password.",
                    )
            # Send response back to client
            response_msg = GenericMessage(
                type=MessageType.RESPONSE, payload=response.model_dump()
            )
            client.socket.send(response_msg.encoded_bytes)

            if (
                response.status == ServerResponseType.SUCCESS
                and auth_req.action == AuthAction.LOGIN
            ):
                notice_user_presence(username, online=True)
                return username
        except (ValidationError, json.JSONDecodeError):
            response = ServerResponse(
                status=ServerResponseType.ERROR,
                content="Invalid authentication request format.",
            )
            response_msg = GenericMessage(
                type=MessageType.RESPONSE, payload=response.model_dump()
            )
            client.socket.send(response_msg.encoded_bytes)


def handle_client(client: ChatClient):
    """
    Hàm xử lý chính cho mỗi client, chạy trong một luồng riêng.
    Điều phối qua 2 giai đoạn: Xác thực và Chat.

    Args:
        client (ChatClient): Đối tượng client mới được chấp nhận.
    """
    peer_name = client.peer_name
    print(f"[NEW CONNECTION] {peer_name} connected.")

    username = None
    try:
        # --- Giai đoạn 1: Xác thực ---
        # Vòng lặp này sẽ block cho đến khi xác thực thành công hoặc thất bại
        username = handle_auth(client)
        if username is None:
            print(f"{peer_name} failed to authenticate.")
            return
        # --- Giai đoạn 2: Chat ---
        print(f"[{username}] has successfully logged in.")
        client.username = username
        with clients_lock:
            clients.append(client)
        handle_chat(client)

    finally:
        # --- Giai đoạn 3: Dọn dẹp ---
        # Bất kể luồng kết thúc như thế nào (lỗi, /quit, mất kết nối),
        # phần này luôn chạy
        print(f"[DISCONNECTED] Disconnected {peer_name}.")
        with clients_lock:
            if client in clients:
                clients.remove(client)
        close_socket(client.socket)


def run():
    """
    Hàm `run` chính của server.
    Khởi tạo, tải dữ liệu và bắt đầu vòng lặp chấp nhận client.
    """
    # Tải (hoặc tạo) file users.csv khi server khởi động
    load_users_df()
    try:
        # Tạo socket lăng nghe kết nối đến
        server_socket = create_server_socket()
    except Exception as e:
        print(f"[ERROR] Failed to start server: {e}")
        return
    # Vòng lặp chính của server, chờ kết nối mới
    while True:
        try:
            # Chấp nhận một kết nối mới (đây là hàm blocking)
            client_socket, _ = server_socket.accept()
            # Tạo đối tượng ChatClient để quản lý client này
            chat_client = ChatClient(socket=client_socket)
            # Tạo một luồng mới để xử lý client này
            # Điều này cho phép server xử lý nhiều client cùng lúc
            thread = threading.Thread(target=handle_client, args=(chat_client,))
            thread.daemon = (
                True  # Đặt là daemon để chương trình chính có thể thoát
                # ngay cả khi các luồng con đang chạy
            )
            thread.start()
        except KeyboardInterrupt:
            print("\nServer shutting down...")
            close_socket(server_socket)
            break
        except Exception as e:
            print(f"[ERROR] Error accepting client connection: {e}")


if __name__ == "__main__":
    run()
