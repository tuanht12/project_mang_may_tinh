import time
from schemas import (
    AuthAction,
    AuthRequest,
    ChatMessage,
    GenericMessage,
    MessageType,
    ServerResponse,
    ServerResponseType,
)
import socket
import threading
from configs import DEFAULT_BUFFER_SIZE, SERVER_HOST, SERVER_PORT, QUIT_COMMAND
from utils import close_socket, get_user_credentials, request_user_login_register
from queue import Queue

MAX_RECONNECTION_ATTEMPTS = 3
SLEEP_BETWEEN_RETRIES = 2  # seconds


def attempt_reconnection(client_credentials):
    """Attempt to reconnect to server"""
    for attempt in range(1, MAX_RECONNECTION_ATTEMPTS + 1):
        print(f"Reconnection attempt {attempt}/{MAX_RECONNECTION_ATTEMPTS}")
        sleep_time = SLEEP_BETWEEN_RETRIES**attempt
        # Try to create new connection
        new_socket = create_connection()
        if new_socket is None:
            time.sleep(sleep_time)
            continue
        # Try to re-authenticate
        is_passed, _ = authenticate_with_server(
            new_socket, AuthAction.LOGIN, client_credentials
        )
        if is_passed:
            print("Reconnected successfully!")
            return new_socket
        else:
            close_socket(new_socket)
            time.sleep(sleep_time)

    print("Failed to reconnect after all attempts")
    return None


def receive_messages(
    client_socket: socket.socket,
    stop_event: threading.Event,
    reconnect_event: threading.Event,
):
    """
    Listens for incoming messages from the server and prints them.
    """
    should_reconnect = False
    while not stop_event.is_set():
        try:
            # Receive message from the server
            generic_message_bytes = client_socket.recv(DEFAULT_BUFFER_SIZE)
            # If no data is received, the server has closed the connection
            if not generic_message_bytes:
                should_reconnect = True
                break
            generic_msg = GenericMessage.model_validate_json(generic_message_bytes)
            if generic_msg.type == MessageType.CHAT:
                chat_msg = ChatMessage.model_validate(generic_msg.payload)
                print(chat_msg.message_string)
            elif generic_msg.type == MessageType.RESPONSE:
                server_resp = ServerResponse.model_validate(generic_msg.payload)
                print(server_resp.message_str)
        except ConnectionResetError:
            print("Connection to the server was lost.")
            should_reconnect = True
            break
        except Exception:
            break
    # Signal other threads to stop
    if should_reconnect and not reconnect_event.is_set():
        reconnect_event.set()
    if not stop_event.is_set():
        stop_event.set()


def send_message_text(message_text: str, client_socket: socket.socket, nickname: str):
    """Send a single message to the server."""
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


def send_messages(
    client_socket: socket.socket,
    nickname: str,
    stop_event: threading.Event,
    reconnect_event: threading.Event,
    message_buffer: Queue,
):
    """
    Takes user input and sends it to the server.
    """
    should_reconnect = False
    while not stop_event.is_set():
        try:
            # Get message from user input
            while not message_buffer.empty():
                message_text = message_buffer.get()
                send_message_text(message_text, client_socket, nickname)
            message_text = input("> ")
            if message_text.strip() == QUIT_COMMAND:
                print("Exiting chat...")
                break
            if reconnect_event.is_set():
                message_buffer.put(message_text)
                break
            send_message_text(message_text, client_socket, nickname)
        except (EOFError, KeyboardInterrupt):
            print("\nDisconnecting...")
            break
        except (ConnectionResetError, BrokenPipeError):
            print("Connection lost during send")
            should_reconnect = True
            break
        except Exception as e:
            print(f"Failed to send message. Connection might be closed. Error: {e}")
            break
    # Signal other threads to stop
    if should_reconnect and not reconnect_event.is_set():
        reconnect_event.set()
    if not stop_event.is_set():
        stop_event.set()  # Signal other threads to stop


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
    except KeyboardInterrupt:
        print("\nClient exiting...")
        return None
    except ConnectionRefusedError:
        print("Connection failed. Is the server running?")
        return None
    except Exception as e:
        print(f"Failed to create connection: {e}")
        return None


def authenticate_with_server(
    client_socket: socket.socket, action: AuthAction, client_credentials: dict
) -> tuple[bool, socket.socket]:
    """
    Attempts to authenticate with the server, with reconnection logic.
    Args:
        client_socket: Socket connection to server
        action: Login or register action
        client_credentials: Dictionary with 'username' and 'password' keys

    Returns:
        tuple[bool, socket.socket]: (success, socket) -
        success status and potentially new socket
    """
    current_socket = client_socket

    auth_req = AuthRequest(
        action=action,
        username=client_credentials["username"],
        password=client_credentials["password"],
    )
    auth_msg = GenericMessage(type=MessageType.AUTH, payload=auth_req.model_dump())

    for attempt in range(1, MAX_RECONNECTION_ATTEMPTS + 1):
        try:
            current_socket.send(auth_msg.encoded_bytes)
            response_bytes = current_socket.recv(DEFAULT_BUFFER_SIZE)
            if not response_bytes:
                print("Server disconnected during authentication.")
                raise ConnectionResetError("Server disconnected")
        except (ConnectionResetError, BrokenPipeError, OSError):
            close_socket(current_socket)
            if attempt == MAX_RECONNECTION_ATTEMPTS:
                print("Failed to authenticate after all reconnection attempts")
                return False, None
            sleep_time = SLEEP_BETWEEN_RETRIES**attempt
            print(
                f"Attempt {attempt}/{MAX_RECONNECTION_ATTEMPTS} "
                f"in {sleep_time} seconds..."
            )
            time.sleep(sleep_time)
            new_socket = create_connection()
            if new_socket is None:
                print(f"Failed to reconnect for authentication attempt {attempt}")
                continue
            else:
                print("Reconnected successfully")
                current_socket = new_socket
                continue
        except Exception as e:
            print(f"Error processing authentication response: {e}")
            return False, None
        break  # Exit loop if no exception occurred

    resp_generic = GenericMessage.model_validate_json(response_bytes)
    if resp_generic.type == MessageType.RESPONSE:
        server_resp = ServerResponse.model_validate(resp_generic.payload)
        print(server_resp.message_str)

        success = (
            server_resp.status == ServerResponseType.SUCCESS
            and action == AuthAction.LOGIN
        )
        return success, current_socket

    return False, current_socket


def perform_authentication(
    client_socket: socket.socket, client_credentials: dict
) -> tuple[str, socket.socket]:
    """
    Handles the complete authentication process.

    Args:
        client_socket: Socket connection to server
        client_credentials: Dictionary to store credentials

    Returns:
        tuple[str, socket.socket]: (username, socket) if successful,
        (None, socket) otherwise
    """
    current_socket = client_socket

    while True:
        try:
            # Get user action (login/register)
            action = request_user_login_register()
            if action is None:
                return None, current_socket

            # Get credentials
            username, password = get_user_credentials()
            if username is None or password is None:
                continue

            # Store credentials for authentication
            client_credentials["username"] = username
            client_credentials["password"] = password

            # Attempt authentication with reconnection logic
            success, new_socket = authenticate_with_server(
                current_socket, action, client_credentials
            )

            if new_socket is None:
                # Authentication failed due to connection issues
                return None, None

            current_socket = new_socket  # Update socket in case it was reconnected

            if success and action == AuthAction.LOGIN:
                return username, current_socket
            else:
                # Authentication failed, but socket is still valid - continue trying
                continue

        except KeyboardInterrupt:
            print("\nExiting authentication...")
            return None, current_socket


def start_chat_session(client_socket: socket.socket, client_credentials: dict):
    """
    Starts the chat session with separate threads for sending and receiving.

    Args:
        client_socket: Authenticated socket connection
        username: Authenticated username
    """
    message_buffer = Queue()
    while True:
        stop_event = threading.Event()
        reconnect_event = threading.Event()
        receive_thread = threading.Thread(
            target=receive_messages, args=(client_socket, stop_event, reconnect_event)
        )
        receive_thread.daemon = True
        receive_thread.start()

        # The main thread handles sending messages
        send_messages(
            client_socket,
            client_credentials["username"],
            stop_event,
            reconnect_event,
            message_buffer,
        )
        # User wants to quit
        if stop_event.is_set() and not reconnect_event.is_set():
            print("Chat session ended.")
            break
        elif reconnect_event.is_set():
            print("Attempting to reconnect...")
            close_socket(client_socket)
            client_socket = attempt_reconnection(client_credentials)
            if client_socket is None:
                print("Could not reconnect. Exiting chat session.")
                break
            else:
                print("Reconnected. You can continue chatting.")
                continue
        else:
            break


def run():
    """
    Main entry point for the chat client.
    Coordinates connection, authentication, and chat session.
    """
    # Establish connection
    client_socket = create_connection()
    if client_socket is None:
        return
    client_credentials = {"username": None, "password": None}
    try:
        # Perform authentication
        username, client_socket = perform_authentication(
            client_socket, client_credentials
        )
        if username is None or client_socket is None:
            print("Exiting...")
            return

        # Start chat session
        start_chat_session(client_socket, client_credentials)
    finally:
        # Always clean up the connection
        if client_socket:
            close_socket(client_socket)


if __name__ == "__main__":
    run()
