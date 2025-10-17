from enum import Enum
from pydantic import BaseModel
import time

from configs import PM_PREFIX, SERVER_NAME


class MessageType(str, Enum):
    AUTH = "auth"
    CHAT = "chat"
    RESPONSE = "response"


class ChatMessage(BaseModel):
    sender: str
    content: str
    timestamp: int

    @property
    def encoded_bytes(self) -> bytes:
        return self.model_dump_json().encode("utf-8")

    @property
    def message_string(self) -> str:
        if self.sender == SERVER_NAME:
            return f"[{self.sender}]: {self.content}"

        human_readable_time = time.strftime(
            "%Y-%m-%d %H:%M:%S", time.localtime(self.timestamp)
        )

        return f"[{human_readable_time}] {self.sender}: {self.content}"

    @property
    def is_private(self) -> bool:
        return (
            self.content.startswith(PM_PREFIX) and len(self.content.split(" ", 2)) == 3
        )


class GenericMessage(BaseModel):
    type: MessageType
    payload: dict

    @property
    def encoded_bytes(self) -> bytes:
        return self.model_dump_json().encode("utf-8")


class AuthAction(str, Enum):
    LOGIN = "login"
    REGISTER = "register"


class AuthRequest(BaseModel):
    action: AuthAction
    username: str
    password: str


class ServerResponse(BaseModel):
    status: str  # 'success' or 'error'
    content: str

    @property
    def message_str(self) -> str:
        return "[SERVER] " + self.content


class ServerResponseType(str, Enum):
    SUCCESS = "success"
    ERROR = "error"
    INFO = "info"
