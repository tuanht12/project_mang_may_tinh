from socket import socket


class ChatClient:
    """Represents a connected client with its socket and username."""

    def __init__(self, socket: socket):
        self.socket = socket
        self.username: str = None

    @property
    def peer_name(self):
        return self.socket.getpeername()

    def __eq__(self, value):
        if not isinstance(value, ChatClient):
            return False
        return self.socket == value.socket
