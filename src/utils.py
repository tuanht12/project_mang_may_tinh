import socket
import time
from schemas import ChatMessage


def convert_message_to_string(message: ChatMessage) -> str:
    human_readable_time = time.strftime(
        "%Y-%m-%d %H:%M:%S", time.localtime(message.timestamp)
    )

    return f"[{human_readable_time}] {message.sender}: {message.content}"


def print_message_in_bytes(message_bytes: bytes):
    message = ChatMessage.model_validate_json(message_bytes.decode("utf-8"))
    print(convert_message_to_string(message))


def get_local_ip():
    """
    Tries to determine the local IP address of the machine.
    Returns '127.0.0.1' on failure.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # This doesn't send any data, it just opens a socket to determine the route.
        s.connect(("8.8.8.8", 1))
        IP = s.getsockname()[0]
    except Exception:
        IP = "127.0.0.1"  # Fallback to loopback address
    finally:
        s.close()
    return IP
