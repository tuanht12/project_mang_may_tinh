from pydantic import BaseModel


class ChatMessage(BaseModel):
    sender: str
    content: str
    timestamp: int

    @property
    def encoded_bytes(self) -> bytes:
        return self.model_dump_json().encode("utf-8")