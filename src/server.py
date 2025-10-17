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
import time

from schemas import (
    AuthAction,
    AuthRequest,
    ChatMessage,
    GenericMessage,
    MessageType,
    ServerResponse,
    ServerResponseStatus,
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
    """Loads the users CSV into a pandas DataFrame.
    Creates the file if it doesn't exist."""
    with csv_lock:
        if not os.path.exists(USERS_CSV):
            os.makedirs(DB_PATH, exist_ok=True)
            df = pd.DataFrame(columns=["username", "password"])
            df.to_csv(USERS_CSV, index=False)
            return df
        return pd.read_csv(USERS_CSV)


def save_users_df(df: pd.DataFrame):
    """Saves the DataFrame back to the CSV file."""
    with csv_lock:
        df.to_csv(USERS_CSV, index=False)


def create_server_socket():
    """Create and return a server socket listening
    on SERVER_HOST and SERVER_PORT
    """
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)  # Reuse address
    server_socket.bind((SERVER_HOST, SERVER_PORT))
    server_socket.listen()
    print(f"Server listening on {SERVER_HOST}:{SERVER_PORT}")
    return server_socket


def send_generic_message_bytes(generic_msg_bytes: bytes, client: ChatClient):
    """Sends a generic message (in bytes) to a specific client."""
    try:
        client.socket.send(generic_msg_bytes)
    except Exception as e:
        print(f"Failed to send message to {client.username}. Error: {e}")
        close_socket(client.socket)
        with clients_lock:
            if client in clients:
                clients.remove(client)


def broadcast(message_bytes: bytes, sending_client: ChatClient):
    """
    Sends a message (in bytes) to all connected clients except the sender.
    """
    with clients_lock:
        for client in clients:
            if client != sending_client:
                send_generic_message_bytes(message_bytes, client)


def handle_private_message(chat_message: ChatMessage, sending_client: ChatClient):
    """Handles sending a private message to a specific recipient."""
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
            error_response = ServerResponse(
                status=ServerResponseStatus.ERROR,
                message=f"User '{recipient}' not found or not online.",
            )
            error_generic_msg = GenericMessage(
                type=MessageType.RESPONSE, payload=error_response.model_dump()
            )
            send_generic_message_bytes(error_generic_msg.encoded_bytes, sending_client)


def handle_get_active_users(sending_client: ChatClient) -> None:
    """Handles the /users command to send the list of active usernames
    to the requesting client."""
    with clients_lock:
        active_usernames = [client.username for client in clients if client.username]
    users_list = "\n".join(active_usernames) if active_usernames else "No users online."
    server_response = ServerResponse(
        status=ServerResponseStatus.SUCCESS,
        message=f"Active users:\n{users_list}",
    )
    server_response_msg = GenericMessage(
        type=MessageType.RESPONSE, payload=server_response.model_dump()
    )
    send_generic_message_bytes(server_response_msg.encoded_bytes, sending_client)


def handle_chat_message(
    generic_msg: GenericMessage, sending_client: ChatClient
) -> None:
    """
    Handles incoming messages from clients.
    """
    chat_message = ChatMessage.model_validate(generic_msg.payload)
    print(chat_message.message_string)  # Log to server console
    if chat_message.is_private:
        handle_private_message(chat_message, sending_client)
    elif chat_message.content.strip() == "/users":
        handle_get_active_users(sending_client)
    else:
        broadcast(generic_msg.encoded_bytes, sending_client)


def handle_chat(client: ChatClient):
    """
    Handles chat messages from an authenticated client.
    """
    while True:
        try:
            generic_message_bytes = client.socket.recv(DEFAULT_BUFFER_SIZE)
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


def is_username_active(username: str) -> bool:
    """Check if a username is already active in the chat."""
    with clients_lock:
        return any(client.username == username for client in clients)


def handle_auth(client: ChatClient):
    """
    Handles authentication for a new client connection.
    This function runs in its own thread for each client.
    Steps:
    1. Receive AuthRequest from the client.
    2. Validate credentials against the users CSV.
    3. Send back a ServerResponse indicating success or failure.
    4. If successful, return the username for further chat handling.
    """
    username = None
    while True:
        auth_bytes = client.socket.recv(DEFAULT_BUFFER_SIZE)
        if not auth_bytes:
            return  # Client disconnected before authentication

        try:
            generic_msg = GenericMessage.model_validate_json(auth_bytes)
            if generic_msg.type != MessageType.AUTH:
                continue  # Ignore non-auth messages during auth phase

            auth_req = AuthRequest.model_validate(generic_msg.payload)
            users_df = load_users_df()

            if auth_req.action == AuthAction.REGISTER:
                if auth_req.username in users_df["username"].values:
                    response = ServerResponse(
                        status=ServerResponseStatus.ERROR,
                        message="Username already exists.",
                    )
                else:
                    users_df = add_new_user_to_db(
                        users_df, auth_req.username, auth_req.password
                    )
                    save_users_df(users_df)
                    response = ServerResponse(
                        status=ServerResponseStatus.SUCCESS,
                        message="Registration successful. Please log in.",
                    )
            elif auth_req.action == AuthAction.LOGIN:
                if verify_user_credentials(
                    users_df, auth_req.username, auth_req.password
                ) and not is_username_active(auth_req.username):
                    response = ServerResponse(
                        status=ServerResponseStatus.SUCCESS,
                        message=get_welcome_message(auth_req.username),
                    )
                    username = auth_req.username
                elif is_username_active(auth_req.username):
                    response = ServerResponse(
                        status=ServerResponseStatus.ERROR,
                        message="This user is already logged in.",
                    )
                else:
                    response = ServerResponse(
                        status=ServerResponseStatus.ERROR,
                        message="Invalid username or password.",
                    )
            # Send response back to client
            response_msg = GenericMessage(
                type=MessageType.RESPONSE, payload=response.model_dump()
            )
            client.socket.send(response_msg.encoded_bytes)

            if (
                response.status == ServerResponseStatus.SUCCESS
                and auth_req.action == AuthAction.LOGIN
            ):
                return username
        except (ValidationError, json.JSONDecodeError):
            response = ServerResponse(
                status=ServerResponseStatus.ERROR,
                message="Invalid authentication request format.",
            )
            response_msg = GenericMessage(
                type=MessageType.RESPONSE, payload=response.model_dump()
            )
            client.socket.send(response_msg.encoded_bytes)


def handle_client(client: ChatClient):
    """
    Handles a new client connection.
    This function runs in its own thread for each client.
    """
    peer_name = client.peer_name
    print(f"[NEW CONNECTION] {peer_name} connected.")

    username = None
    try:
        # --- Authentication Phase ---
        username = handle_auth(client)
        if username is None:
            print(f"{peer_name} failed to authenticate.")
            return
        # --- Chat Phase ---
        print(f"[{username}] has successfully logged in.")
        client.username = username
        with clients_lock:
            clients.append(client)
        handle_chat(client)

    finally:
        # --- Cleanup ---
        print(f"[DISCONNECTED] Disconnected {peer_name}.")
        with clients_lock:
            if client in clients:
                clients.remove(client)
        close_socket(client.socket)

# ===== RECONNECT PATCH (add-only) =====
# Place this block ABOVE the "if __name__ == '__main__':" line.



# Lưu bản gốc để fallback khi cần (không bắt buộc dùng hết)
_original_receive_messages = receive_messages
_original_send_messages = send_messages
_original_authenticate_with_server = authenticate_with_server

# --- State & config nhẹ ---
_RECONNECT_LOCK = threading.Lock()
_CURRENT_SOCKET: socket.socket | None = None
_LAST_AUTH: dict | None = None   # {'username': str, 'password': str}
_RETRY_BACKOFFS = [0.5, 1, 2, 3, 5, 8, 13]  # giây
_OUTBOX: list[str] = []
def _set_current_socket(s: socket.socket | None):
    global _CURRENT_SOCKET
    _CURRENT_SOCKET = s

def _get_current_socket() -> socket.socket | None:
    return _CURRENT_SOCKET

def _attempt_reconnect() -> socket.socket | None:
    """Cố gắng kết nối lại + LOGIN bằng thông tin lần trước (ghi nhớ khi login thành công)."""
    if _LAST_AUTH is None:
        print("[client] Chưa có thông tin đăng nhập để reconnect. Gõ /quit rồi chạy lại.")
        return None

    with _RECONNECT_LOCK:
        # Nếu thread kia đã reconnect xong
        s = _get_current_socket()
        if s is not None:
            return s

        print("[client] Mất kết nối. Đang thử reconnect ...")
        for i, delay in enumerate(_RETRY_BACKOFFS, start=1):
            try:
                s = create_connection()
                if s is None:
                    raise RuntimeError("connect() failed")

                ok = _original_authenticate_with_server(
                    s, AuthAction.LOGIN, _LAST_AUTH["username"], _LAST_AUTH["password"]
                )
                if ok:
                    _set_current_socket(s)
                    print(f"[client] Reconnected as '{_LAST_AUTH['username']}' (attempt {i}).")
                    return s
                else:
                    try:
                        close_socket(s)
                    except Exception:
                        pass
            except Exception:
                pass

            print(f"[client] Reconnect attempt {i} failed. Retrying in {delay}s ...")
            time.sleep(delay)

        print("[client] Reconnect failed. Sẽ tiếp tục thử khi bạn gửi/nhận lần sau.")
        return None

# --- override: lưu thông tin đăng nhập khi LOGIN thành công để dùng cho reconnect ---
def authenticate_with_server(client_socket: socket.socket, action: AuthAction, username: str, password: str) -> bool:
    ok = _original_authenticate_with_server(client_socket, action, username, password)
    if ok and action == AuthAction.LOGIN:
        # Ghi nhớ để tự LOGIN khi reconnect
        global _LAST_AUTH
        _LAST_AUTH = {"username": username, "password": password}
        _set_current_socket(client_socket)
    return ok

# --- override: nhận tin có auto-reconnect ---
def receive_messages(client_socket: socket.socket, stop_event: threading.Event):
    # gắn socket hiện tại cho patch (lần đầu)
    if _get_current_socket() is None:
        _set_current_socket(client_socket)

    while not stop_event.is_set():
        s = _get_current_socket()
        if s is None:
            # chưa có socket → thử reconnect
            s = _attempt_reconnect()
            if s is None:
                time.sleep(0.5)
                continue

        try:
            data = s.recv(DEFAULT_BUFFER_SIZE)
            if not data:
                # server đóng → reset và vào vòng reconnect
                _set_current_socket(None)
                continue

            generic_msg = GenericMessage.model_validate_json(data)
            if generic_msg.type == MessageType.CHAT:
                chat_msg = ChatMessage.model_validate(generic_msg.payload)
                print(chat_msg.message_string)
            elif generic_msg.type == MessageType.RESPONSE:
                server_resp = ServerResponse.model_validate(generic_msg.payload)
                print(f"[SERVER]: {server_resp.message}")

        except (ConnectionResetError, ConnectionAbortedError, OSError):
            # socket dead → clear & reconnect
            _set_current_socket(None)
            continue
        except Exception:
            # lỗi parse v.v... không giết luồng
            continue

# --- override: gửi tin có auto-reconnect (+ lệnh /reconnect thủ công) ---
def send_messages(client_socket: socket.socket, nickname: str, stop_event: threading.Event):
    # gắn socket hiện tại cho patch (lần đầu)
    if _get_current_socket() is None:
        _set_current_socket(client_socket)

    while not stop_event.is_set():
        try:
            text = input("> ")
        except (EOFError, KeyboardInterrupt):
            print("\nDisconnecting...")
            break

        if not text:
            continue
        if text.strip() == QUIT_COMMAND:
            print("Exiting chat...")
            break
        if text.strip().lower() in ("/re", "/reconnect"):
            _set_current_socket(None)
            _attempt_reconnect()
            continue

        # Gửi với 1 lần retry sau khi reconnect
        sent = False
        for attempt in (1, 2):
            s = _get_current_socket()
            if s is None:
                s = _attempt_reconnect()
                if s is None:
                    break

            try:
                chat_msg = ChatMessage(sender=nickname, content=text, timestamp=int(time.time()))
                generic_msg = GenericMessage(type=MessageType.CHAT, payload=chat_msg.model_dump())
                s.send(generic_msg.encoded_bytes)
                sent = True
                break
            except (ConnectionResetError, ConnectionAbortedError, OSError):
                _set_current_socket(None)
                if attempt == 1:
                    print("[client] Send failed. Reconnecting ...")
                    continue
                else:
                    break
            except Exception:
                # lỗi khác → không retry vô hạn
                break

        if not sent:
            print("[client] Gửi thất bại. Thử lại nhé!")


# ===== END RECONNECT PATCH =====

LOG_DIR = "logs"
_history_lock = threading.Lock()

def _ensure_log_dir():
    os.makedirs(LOG_DIR, exist_ok=True)

def _safe_filename(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_\-]", "_", name)

def _dm_log_filename(a: str, b: str) -> str:
    a1, b1 = sorted([a, b], key=str.lower)
    return os.path.join(LOG_DIR, f"dm__{_safe_filename(a1)}__{_safe_filename(b1)}.log")

def _room_log_filename(room: str) -> str:
    return os.path.join(LOG_DIR, f"room__{_safe_filename(room)}.log")

def _append_history_line(path: str, line: str):
    _ensure_log_dir()
    with _history_lock:
        with open(path, "a", encoding="utf-8") as f:
            f.write(line.rstrip("\n") + "\n")

def _tail_history(path: str, n: int = 20) -> str:
    if not os.path.exists(path):
        return "(no history)"
    with _history_lock:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    last = "".join(lines[-n:])
    return last or "(no history)"

# --- Save originals to wrap ---
_original_broadcast = broadcast
_original_handle_private_message = handle_private_message
_original_handle_chat_message = handle_chat_message

# --- Wrap broadcast: log all public chats to 'global' ---
def broadcast(message_bytes: bytes, sending_client: ChatClient):
    # Keep original behavior
    _original_broadcast(message_bytes, sending_client)
    # Best-effort decode and log
    try:
        generic_msg = GenericMessage.model_validate_json(message_bytes)
        if generic_msg.type == MessageType.CHAT:
            chat = ChatMessage.model_validate(generic_msg.payload)
            # One global room (main code has no rooms)
            _append_history_line(
                _room_log_filename("global"),
                f"{chat.timestamp}\t{chat.sender}\t{chat.content}",
            )
    except Exception:
        pass

# --- Wrap private message: also log to dm__A__B.log ---
def handle_private_message(chat_message: ChatMessage, sending_client: ChatClient):
    _original_handle_private_message(chat_message, sending_client)
    try:
        # content format: "/pm <recipient> <message...>"
        _, recipient, content = chat_message.content.split(" ", 2)
        _append_history_line(
            _dm_log_filename(chat_message.sender, recipient),
            f"{chat_message.timestamp}\t{chat_message.sender}\t{content}",
        )
    except Exception:
        pass

# --- Wrap chat handler: add '/history' commands ---
def handle_chat_message(generic_msg: GenericMessage, sending_client: ChatClient) -> None:
    try:
        chat_message = ChatMessage.model_validate(generic_msg.payload)
    except Exception:
        # Fallback to original if anything odd
        return _original_handle_chat_message(generic_msg, sending_client)

    text = (chat_message.content or "").strip()
    if text.startswith("/history"):
        parts = text.split()
        # /history @user [N]
        if len(parts) >= 2 and parts[1].startswith("@"):
            target = parts[1][1:]
            n = int(parts[2]) if len(parts) >= 3 and parts[2].isdigit() else 20
            path = _dm_log_filename(chat_message.sender, target)
            out = _tail_history(path, n)
            resp = ServerResponse(
                status=ServerResponseStatus.SUCCESS,
                message=f"DM history @{target} (last {n}):\n{out}",
            )
        else:
            # /history [N]
            n = int(parts[1]) if len(parts) >= 2 and parts[1].isdigit() else 20
            path = _room_log_filename("global")
            out = _tail_history(path, n)
            resp = ServerResponse(
                status=ServerResponseStatus.SUCCESS,
                message=f"Global history (last {n}):\n{out}",
            )

        resp_msg = GenericMessage(type=MessageType.RESPONSE, payload=resp.model_dump())
        send_generic_message_bytes(resp_msg.encoded_bytes, sending_client)
        return

    # Not a history command → original behavior
    _original_handle_chat_message(generic_msg, sending_client)

def main():
    """
    Main server loop to accept incoming client connections.
    """
    try:
        server_socket = create_server_socket()
    except Exception as e:
        print(f"[ERROR] Failed to start server: {e}")
        return

    while True:
        try:
            client_socket, _ = server_socket.accept()
            chat_client = ChatClient(socket=client_socket)
            thread = threading.Thread(target=handle_client, args=(chat_client,))
            thread.daemon = (
                True  # Allows main program to exit even if threads are running
            )
            thread.start()
        except KeyboardInterrupt:
            print("\nServer shutting down...")
            close_socket(server_socket)
            break
        except Exception as e:
            print(f"[ERROR] Error accepting client connection: {e}")



if __name__ == "__main__":
    load_users_df()  # Ensure users CSV exists on startup
    main()
