import socket

import pandas as pd


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
    current_password = str(user_row["password"].iloc[0])
    return current_password == password


def close_socket(sock: socket.socket):
    """Gracefully close a socket."""
    if sock.fileno() == -1:
        return
    try:
        sock.shutdown(socket.SHUT_RDWR)
    except OSError:  # Socket already closed or not connected
        pass
    finally:
        sock.close()
