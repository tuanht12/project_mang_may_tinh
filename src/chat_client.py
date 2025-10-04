import time
from schemas import ChatMessage
import socket
import threading
from configs import DEFAULT_BUFFER_SIZE, SERVER_HOST, SERVER_PORT
from utils import print_message_in_bytes


def receive_messages(client_socket: socket.socket):
    """
    Listens for incoming messages from the server and prints them.
    """
    while True:
        try:
            # Receive message from the server
            message_bytes = client_socket.recv(DEFAULT_BUFFER_SIZE)
            if not message_bytes:
                # If the server closes the connection, recv returns an empty string
                print("Disconnected from server.")
                break
            print_message_in_bytes(message_bytes)
        except ConnectionResetError:
            print("Connection to the server was lost.")
            break
        except Exception as e:
            print(f"An error occurred: {e}")
            client_socket.close()
            break


def send_messages(client_socket: socket.socket):
    """
    Takes user input and sends it to the server.
    """
    nickname = input("Choose your nickname: ")

    while True:
        # Get message from user input
        message_text = input("> ")

        # Format the message with the nickname
        message = ChatMessage(
            sender=nickname, content=message_text, timestamp=int(time.time())
        )

        try:
            # Send the message to the server
            client_socket.send(message.encoded_bytes)
        except Exception as e:
            print(f"Failed to send message. Connection might be closed. Error: {e}")
            break


def start_client():
    """
    Initializes and starts the chat client.
    """
    # Create a TCP/IP socket
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    try:
        # Connect the socket to the server's address and port
        client_socket.connect((SERVER_HOST, SERVER_PORT))
    except ConnectionRefusedError:
        print("Connection failed. Is the server running?")
        return

    # --- Start threads for sending and receiving messages ---
    receive_thread = threading.Thread(target=receive_messages, args=(client_socket,))
    receive_thread.daemon = True
    receive_thread.start()

    # The main thread will handle sending messages
    send_messages(client_socket)

    # --- Cleanup ---
    client_socket.close()


if __name__ == "__main__":
    start_client()
