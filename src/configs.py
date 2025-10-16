import os
from pathlib import Path

# Connection settings


SERVER_HOST = "127.0.0.1"  # Change this to IPV4 address of your server
SERVER_PORT = 65432
DEFAULT_BUFFER_SIZE = 1024

# Server settings
CUR_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = "db"
USERS_CSV = os.path.join(DB_PATH, "users.csv")  # Path to the CSV file storing user data

# Command prefixes
PM_PREFIX = "/pm "  # Prefix for private messages
QUIT_COMMAND = "/quit"


def get_welcome_message(username: str) -> str:
    msg = f"""Welcome to the chat, {username}!

    Instructions:
    - Type your message and hit enter to send it.
    - Use {PM_PREFIX}username your_message to send a private message.
    - Type {QUIT_COMMAND} to exit the chat."""
    return msg.replace("\t", " ").replace("    ", " ").strip()
