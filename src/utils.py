import socket
import time

import pandas as pd
from schemas import ChatMessage


def convert_message_to_string(message: ChatMessage) -> str:
    human_readable_time = time.strftime(
        "%Y-%m-%d %H:%M:%S", time.localtime(message.timestamp)
    )

    return f"[{human_readable_time}] {message.sender}: {message.content}"


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


def add_new_user_to_db(
    current_df: pd.DataFrame, username: str, password: str
) -> pd.DataFrame:
    if username in current_df["username"].values:
        return current_df  # Username already exists
    new_user = pd.DataFrame({"username": [username], "password": [password]})
    current_df = pd.concat([current_df, new_user], ignore_index=True)
    return current_df


def verify_user_credentials(df: pd.DataFrame, username: str, password: str) -> bool:
    user_row = df[df["username"] == username]
    if user_row.empty:
        return False
    current_password = user_row.iloc[0]["password"].astype(str)
    return current_password == password
