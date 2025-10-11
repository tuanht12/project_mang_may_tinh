import time
from schemas import ChatMessage, GenericMessage, MessageType
import socket
import threading
from configs import DEFAULT_BUFFER_SIZE, SERVER_HOST, SERVER_PORT
from utils import convert_message_to_string


def receive_messages(client_socket: socket.socket):
    """
    Listens for incoming messages from the server and prints them.
    """
    while True:
        try:
            # Receive message from the server
            generic_message_bytes = client_socket.recv(DEFAULT_BUFFER_SIZE)
            if not generic_message_bytes:
                # If the server closes the connection, recv returns an empty string
                print("Disconnected from server.")
                break
            generic_msg = GenericMessage.model_validate_json(generic_message_bytes)
            if generic_msg.type == MessageType.CHAT:
                chat_msg = ChatMessage.model_validate(generic_msg.payload)
                print(convert_message_to_string(chat_msg))
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
        try:
            # Get message from user input
            message_text = input("> ")
            if message_text:
                # Format the message with the nickname
                chat_msg = ChatMessage(
                    sender=nickname, content=message_text, timestamp=int(time.time())
                )
                generic_msg = GenericMessage(
                    type=MessageType.CHAT, payload=chat_msg.model_dump()
                )

                # Send the message to the server
                client_socket.send(generic_msg.encoded_bytes)
        except (EOFError, KeyboardInterrupt):
            print("\nDisconnecting...")
            break
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
