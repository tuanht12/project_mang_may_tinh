from typing import List, Dict
from configs import DEFAULT_BUFFER_SIZE, SERVER_PORT, SERVER_HOST
import socket
import threading
from utils import print_message_in_bytes

# --- State ---
clients: List[Dict[str, any]] = []  # Each client is a dict: {"socket": ..., "username": ...}
clients_lock = threading.Lock()


def create_server_socket():
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind((SERVER_HOST, SERVER_PORT))
    server_socket.listen()
    print(f"Server listening on {SERVER_HOST}:{SERVER_PORT}")
    return server_socket


def broadcast(message_bytes: bytes, sender_socket: socket.socket = None):
    with clients_lock:
        for client in clients:
            try:
                if sender_socket is None or client["socket"] != sender_socket:
                    client["socket"].send(message_bytes)
            except Exception as e:
                print(f"Failed to send message to a client. Error: {e}")
                client["socket"].close()
                clients.remove(client)


def get_online_usernames() -> List[str]:
    return [client["username"] for client in clients]


def send_online_users_list():
    usernames = get_online_usernames()
    message = f"[SERVER] Online users: {', '.join(usernames)}".encode("utf-8")
    broadcast(message)


def handle_client(client_socket: socket.socket):
    try:
        # Nhận username
        username_bytes = client_socket.recv(DEFAULT_BUFFER_SIZE)
        username = username_bytes.decode("utf-8").strip()
        print(f"[NEW CONNECTION] {username} ({client_socket.getpeername()}) connected.")

        with clients_lock:
            clients.append({"socket": client_socket, "username": username})

        # Gửi thông báo join đến tất cả clients
        join_message = f"[SERVER] {username} has joined the chat.".encode("utf-8")
        broadcast(join_message, sender_socket=client_socket)
        send_online_users_list()

        # Xử lý các tin nhắn gửi từ client
        while True:
            message_byte = client_socket.recv(DEFAULT_BUFFER_SIZE)
            if not message_byte:
                break
            print_message_in_bytes(message_byte)
            broadcast(message_byte, sender_socket=client_socket)

    except ConnectionResetError:
        print(f"[DISCONNECTED] {client_socket.getpeername()} disconnected unexpectedly.")
    except Exception as e:
        print(f"[ERROR] {e}")

    # Client rời khỏi phòng
    with clients_lock:
        leaving_client = next((c for c in clients if c["socket"] == client_socket), None)
        if leaving_client:
            clients.remove(leaving_client)
            leave_message = f"[SERVER] {leaving_client['username']} has left the chat.".encode("utf-8")
            broadcast(leave_message)
            send_online_users_list()

    client_socket.close()


if __name__ == "__main__":
    server_socket = create_server_socket()

    while True:
        client_socket, addr = server_socket.accept()
        thread = threading.Thread(target=handle_client, args=(client_socket,))
        thread.daemon = True
        thread.start()
