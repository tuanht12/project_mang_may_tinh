import getpass
import time
from schemas import (
    AuthRequest,
    ChatMessage,
    GenericMessage,
    MessageType,
    ServerResponse,
)
import socket
import threading
from configs import DEFAULT_BUFFER_SIZE, SERVER_HOST, SERVER_PORT

QUIT_COMMAND = "/quit"


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
                print(chat_msg.message_string)
        except ConnectionResetError:
            print("Connection to the server was lost.")
            break
        except Exception as e:
            print(f"An error occurred: {e}")
            client_socket.close()
            break


def send_messages(client_socket: socket.socket, nickname: str):
    """
    Takes user input and sends it to the server.
    """
    while True:
        try:
            # Get message from user input
            message_text = input("> ")
            if message_text.strip() == QUIT_COMMAND:
                print("Exiting chat...")
                break
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

    client_username = None
    while client_username is None:
        action = input("Select '1' to login, '2' to register: ").strip()
        action = "login" if action == "1" else "register" if action == "2" else ""
        if action not in ["login", "register"]:
            print("Invalid option. Please choose '1' or '2'.")
            continue
        username = input("Enter username: ").strip()
        password = getpass.getpass("Enter password: ")  # Hides password input

        auth_req = AuthRequest(action=action, username=username, password=password)
        generic_msg = GenericMessage(
            type=MessageType.AUTH, payload=auth_req.model_dump()
        )
        try:
            client_socket.send(generic_msg.encoded_bytes)

            response_bytes = client_socket.recv(DEFAULT_BUFFER_SIZE)
            if not response_bytes:
                print("Server disconnected during authentication.")
                return

            resp_generic = GenericMessage.model_validate_json(response_bytes)
            if resp_generic.type == MessageType.RESPONSE:
                server_resp = ServerResponse.model_validate(resp_generic.payload)
                print(f"[SERVER]: {server_resp.message}")

                if server_resp.status == "success" and action == "login":
                    client_username = username
                    break  # Exit the authentication loop
        except Exception as e:
            print(f"An error occurred during authentication: {e}")
            break
    # --- Start threads for sending and receiving messages ---
    if client_username:
        receive_thread = threading.Thread(
            target=receive_messages, args=(client_socket,)
        )
        receive_thread.daemon = True
        receive_thread.start()

        # The main thread will handle sending messages
        send_messages(client_socket, client_username)

    # --- Cleanup ---
    client_socket.close()


if __name__ == "__main__":
    start_client()
