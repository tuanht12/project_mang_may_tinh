import getpass
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


def create_connection() -> socket.socket:
    """
    Creates and establishes a connection to the server.

    Returns:
        socket.socket: Connected socket or None if connection fails
    """
    try:
        client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client_socket.connect((SERVER_HOST, SERVER_PORT))
        return client_socket
    except ConnectionRefusedError:
        print("Connection failed. Is the server running?")
        return None
    except Exception as e:
        print(f"Failed to create connection: {e}")
        return None


def get_user_action() -> AuthAction:
    """
    Prompts user to select login or register action.

    Returns:
        AuthAction: Selected action or None if user wants to quit
    """
    while True:
        action = input(
            f"Select '1' to {AuthAction.LOGIN.value}, '2' to {AuthAction.REGISTER.value},"
            f"'{QUIT_COMMAND}' to quit: "
        ).strip()

        if action == QUIT_COMMAND:
            return None

        if action == "1":
            return AuthAction.LOGIN
        elif action == "2":
            return AuthAction.REGISTER
        else:
            print("Invalid option. Please choose '1' or '2'.")


def get_user_credentials() -> tuple[str, str]:
    """
    Prompts user for username and password.

    Returns:
        tuple[str, str]: (username, password) or (None, None) if invalid
    """
    username = input("Enter username: ").strip()
    password = getpass.getpass("Enter password: ")

    if not username or not password:
        print("Username and password cannot be empty.")
        return None, None

    return username, password


def authenticate_with_server(
    client_socket: socket.socket, action: AuthAction, username: str, password: str
) -> bool:
    """
    Sends authentication request to server and handles response.

    Args:
        client_socket: Socket connection to server
        action: Login or register action
        username: User's username
        password: User's password

    Returns:
        bool: True if authentication successful, False otherwise
    """
    try:
        # Send authentication request
        auth_req = AuthRequest(action=action, username=username, password=password)
        auth_msg = GenericMessage(type=MessageType.AUTH, payload=auth_req.model_dump())
        client_socket.send(auth_msg.encoded_bytes)

        # Receive and process response
        response_bytes = client_socket.recv(DEFAULT_BUFFER_SIZE)
        if not response_bytes:
            print("Server disconnected during authentication.")
            return False

        resp_generic = GenericMessage.model_validate_json(response_bytes)
        if resp_generic.type == MessageType.RESPONSE:
            server_resp = ServerResponse.model_validate(resp_generic.payload)
            print(f"[SERVER]: {server_resp.message}")

            return (
                server_resp.status == ServerResponseStatus.SUCCESS
                and action == AuthAction.LOGIN
            )

        return False

    except Exception as e:
        print(f"An error occurred during authentication: {e}")
        return False


def perform_authentication(client_socket: socket.socket) -> str:
    """
    Handles the complete authentication process.

    Args:
        client_socket: Socket connection to server

    Returns:
        str: Username if authentication successful, None otherwise
    """
    while True:
        # Get user action (login/register)
        action = get_user_action()
        if action is None:
            return None

        # Get credentials
        username, password = get_user_credentials()
        if username is None or password is None:
            continue

        # Attempt authentication
        if (
            authenticate_with_server(client_socket, action, username, password)
            and action == AuthAction.LOGIN
        ):
            return username
        else:
            continue


def start_chat_session(client_socket: socket.socket, username: str):
    """
    Starts the chat session with separate threads for sending and receiving.

    Args:
        client_socket: Authenticated socket connection
        username: Authenticated username
    """
    receive_thread = threading.Thread(target=receive_messages, args=(client_socket,))
    receive_thread.daemon = True
    receive_thread.start()

    # The main thread handles sending messages
    send_messages(client_socket, username)


def start_client():
    """
    Main entry point for the chat client.
    Coordinates connection, authentication, and chat session.
    """
    # Establish connection
    client_socket = create_connection()
    if client_socket is None:
        return

    try:
        # Perform authentication
        username = perform_authentication(client_socket)
        if username is None:
            print("Exiting...")
            return

        # Start chat session
        start_chat_session(client_socket, username)

    except KeyboardInterrupt:
        print("\nShutting down...")
    except Exception as e:
        print(f"Unexpected error: {e}")
    finally:
        # Cleanup
        client_socket.close()
        print("Chat session ended.")


if __name__ == "__main__":
    start_client()
