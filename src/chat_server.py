import json
from typing import List

from pydantic import ValidationError
from configs import DEFAULT_BUFFER_SIZE, SERVER_PORT, SERVER_HOST
import socket
import threading
from schemas import (
    AuthAction,
    AuthRequest,
    ChatMessage,
    GenericMessage,
    MessageType,
    ServerResponse,
)
from utils import convert_message_to_string, add_new_user_to_db, verify_user_credentials
import pandas as pd
import os

# --- State ---
# List to keep track of all connected client sockets
clients: List[socket.socket] = []
# Lock to ensure that the clients list is accessed by only one thread at a time
clients_lock = threading.Lock()
DB_PATH = "db"
USERS_CSV = os.path.join(DB_PATH, "users.csv")  # Path to the CSV file storing user data
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


def broadcast(message_bytes: bytes, sender_socket: socket.socket):
    """
    Sends a message (in bytes) to all connected clients except the sender.
    """
    with clients_lock:
        for client in clients:
            if client != sender_socket:
                try:
                    client.send(message_bytes)
                except Exception as e:
                    print(f"Failed to send message to a client. Error: {e}")
                    client.close()
                    clients.remove(client)


def handle_chat(client_socket: socket.socket):
    """
    Handles chat messages from an authenticated client.
    """
    while True:
        try:
            generic_message_bytes = client_socket.recv(DEFAULT_BUFFER_SIZE)
            if not generic_message_bytes:
                break

            generic_msg = GenericMessage.model_validate_json(generic_message_bytes)
            if generic_msg.type == MessageType.CHAT:
                chat_msg = ChatMessage.model_validate(generic_msg.payload)
                print(convert_message_to_string(chat_msg))
                broadcast(generic_message_bytes, client_socket)

        except ConnectionResetError:
            # Handle the case where the client forcefully closes the connection
            print(
                f"[DISCONNECTED] {client_socket.getpeername()}"
                f" disconnected unexpectedly."
            )
            break
        except Exception as e:
            print(f"[ERROR] {e}")
            break


def handle_client(client_socket: socket.socket):
    """
    Handles a new client connection, starting with authentication.
    This function runs in its own thread for each client.
    Steps:
    1. Authenticate the user.
    2. If authentication is successful, start handling chat messages.
    3. If authentication fails, close the connection.
    """
    print(f"[NEW CONNECTION] {client_socket.getpeername()} connected.")
    username = None
    try:
        while True:
            auth_bytes = client_socket.recv(DEFAULT_BUFFER_SIZE)
            if not auth_bytes:
                print(f"[DISCONNECTED] {client_socket.getpeername()} disconnected.")
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
                            status="error", message="Username already exists."
                        )
                    else:
                        users_df = add_new_user_to_db(
                            users_df, auth_req.username, auth_req.password
                        )
                        save_users_df(users_df)
                        response = ServerResponse(
                            status="success",
                            message="Registration successful. Please log in.",
                        )
                elif auth_req.action == AuthAction.LOGIN:
                    if verify_user_credentials(
                        users_df, auth_req.username, auth_req.password
                    ):
                        response = ServerResponse(
                            status="success",
                            message=f"Login successful. Welcome {auth_req.username}!",
                        )
                        username = auth_req.username
                    else:
                        response = ServerResponse(
                            status="error", message="Invalid username or password."
                        )
                # Send response back to client
                response_msg = GenericMessage(
                    type=MessageType.RESPONSE, payload=response.model_dump()
                )
                client_socket.send(response_msg.encoded_bytes)

                if response.status == "success" and auth_req.action == AuthAction.LOGIN:
                    break  # Exit auth loop on successful login
            except (ValidationError, json.JSONDecodeError):
                response = ServerResponse(
                    status="error", message="Invalid authentication request format."
                )
                response_msg = GenericMessage(
                    type=MessageType.RESPONSE, payload=response.model_dump()
                )
                client_socket.send(response_msg.encoded_bytes)

        # --- Chat Phase ---
        print(f"[{username}] has successfully logged in.")
        with clients_lock:
            clients.append(client_socket)
        handle_chat(client_socket)

    finally:
        # --- Cleanup ---
        print(f"[DISCONNECTED] {username or client_socket.getpeername()} disconnected.")
        with clients_lock:
            if client_socket in clients:
                clients.remove(client_socket)
        client_socket.close()


if __name__ == "__main__":
    load_users_df()  # Ensure users CSV exists on startup
    server_socket = create_server_socket()

    while True:
        client_socket, addr = server_socket.accept()

        thread = threading.Thread(target=handle_client, args=(client_socket,))
        thread.daemon = True  # Allows main program to exit even if threads are running
        thread.start()
