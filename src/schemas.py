from enum import Enum
from pydantic import BaseModel


class ChatMessage(BaseModel):
    sender: str
    content: str
    timestamp: int

    @property
    def encoded_bytes(self) -> bytes:
        return self.model_dump_json().encode("utf-8")


class MessageType(str, Enum):
    AUTH = "auth"
    CHAT = "chat"
    RESPONSE = "response"


class AuthAction(str, Enum):
    LOGIN = "login"
    REGISTER = "register"


class AuthRequest(BaseModel):
    action: AuthAction
    username: str
    password: str


class ServerResponse(BaseModel):
    status: str  # 'success' or 'error'
    message: str


class GenericMessage(BaseModel):
    type: MessageType
    payload: dict

    @property
    def encoded_bytes(self) -> bytes:
        return self.model_dump_json().encode("utf-8")
