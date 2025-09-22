from configs import SERVER_HOST, SERVER_PORT
import socket
import time
import random
import threading


def create_server_socket():
    """Create and return a server socket.
    AF_INET: IPv4
    SOCK_STREAM: TCP
    """
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.bind((SERVER_HOST, SERVER_PORT))
    server_socket.listen()
    print(f"Server listening on {SERVER_HOST}:{SERVER_PORT}")
    return server_socket


def get_random_message():

    messages = [
        "Hello from server!",
        "How are you?",
        "This is a test message.",
        "Have a great day!",
        "Server says hi!",
    ]
    return random.choice(messages)


def send_random_messages(client_socket):
    """Send random messages to the client every 5 seconds"""
    while True:
        time.sleep(5)
        random_msg = get_random_message()
        client_socket.sendall(f"SERVER MESSAGE: {random_msg}".encode("utf-8"))


def receive_and_echo(client_socket):
    """Receive messages from client and echo back"""
    while True:
        data = client_socket.recv(1024)
        if not data:
            break
        client_msg = data.decode("utf-8")
        print(f"Received from client: {client_msg}")
        response_msg = f"SERVER DA NHAN DUOC: {client_msg}"
        client_socket.sendall(response_msg.encode("utf-8"))


if __name__ == "__main__":
    server_socket = create_server_socket()

    while True:
        client_socket, addr = server_socket.accept()
        print(f"Connection from {addr} has been established.")
        # client_socket.sendall(b"Welcome to the server!")

        send_random_thread = threading.Thread(
            target=send_random_messages, args=(client_socket,)
        )
        send_random_thread.start()

        receive_and_echo_thread = threading.Thread(
            target=receive_and_echo, args=(client_socket,)
        )
        receive_and_echo_thread.start()
