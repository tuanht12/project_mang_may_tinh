import socket
from configs import SERVER_HOST, SERVER_PORT
import threading


def receive_messages(client_socket):
    """Continuously receive messages from server"""
    while True:
        try:
            data = client_socket.recv(1024)
            if not data:
                break
            server_msg = data.decode("utf-8")
            print(f"Received from server: {server_msg}")
        except:
            break


def send_messages(client_socket):
    """Continuously send messages to server"""
    while True:
        msg = input()
        if msg.lower() == "exit":
            break
        client_socket.sendall(msg.encode("utf-8"))


def start_client():
    """Starts a simple client that connects to the server"""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect((SERVER_HOST, SERVER_PORT))
    return s


if __name__ == "__main__":
    client_socket = start_client()
    receive_thread = threading.Thread(target=receive_messages, args=(client_socket,))
    send_thread = threading.Thread(target=send_messages, args=(client_socket,))
    receive_thread.start()
    send_thread.start()
    receive_thread.join()
    send_thread.join()
    