from typing import List
from configs import DEFAULT_BUFFER_SIZE, SERVER_PORT, SERVER_HOST
import socket
import threading
from schemas import ChatMessage, GenericMessage, MessageType
from utils import convert_message_to_string
import pandas as pd
import os

# --- State ---
# List to keep track of all connected client sockets
clients: List[socket.socket] = []
# Lock to ensure that the clients list is accessed by only one thread at a time
clients_lock = threading.Lock()

USERS_CSV = "users.csv"  # Path to the CSV file storing user data
csv_lock = threading.Lock()  # Lock for accessing the CSV file


def load_users_df():
    """Loads the users CSV into a pandas DataFrame. Creates the file if it doesn't exist."""
    with csv_lock:
        if not os.path.exists(USERS_CSV):
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
    Handles a single client connection. This function will be run in its own thread.
    """
    print(f"[NEW CONNECTION] {client_socket.getpeername()} connected.")

    handle_chat(client_socket)

    # When the loop breaks, the client has disconnected.
    print(f"[DISCONNECTED] {client_socket.getpeername()} disconnected.")
    with clients_lock:
        if client_socket in clients:
            clients.remove(client_socket)
    client_socket.close()


if __name__ == "__main__":
    server_socket = create_server_socket()

    while True:
        client_socket, addr = server_socket.accept()

        with clients_lock:
            clients.append(client_socket)

        thread = threading.Thread(target=handle_client, args=(client_socket,))
        thread.daemon = True  # Allows main program to exit even if threads are running
        thread.start()
