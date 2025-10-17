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
                status=ServerResponseType.ERROR,
                content=f"User '{recipient}' not found or not online.",
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
        status=ServerResponseType.SUCCESS,
        content=f"Active users:\n{users_list}",
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
    notice_user_presence(client.username, online=False)


def is_username_active(username: str) -> bool:
    """Check if a username is already active in the chat."""
    with clients_lock:
        return any(client.username == username for client in clients)


def notice_user_presence(username: str, online: bool):
    """Notify all clients about a user's presence change."""
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
