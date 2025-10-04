from pydantic import BaseModel


class ChatMessage(BaseModel):
    sender: str
    content: str
    timestamp: int
