import getpass
import socket

import pandas as pd

from configs import QUIT_COMMAND
from schemas import AuthAction


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


def request_user_login_register() -> AuthAction:
    """
    Prompts user to select login or register action.

    Returns:
        AuthAction: Selected action or None if user wants to quit
    """
    while True:
        action = input(
            f"Select '1' to {AuthAction.LOGIN.value},"
            f"'2' to {AuthAction.REGISTER.value},"
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
