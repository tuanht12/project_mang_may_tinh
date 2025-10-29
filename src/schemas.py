"""\
Module này định nghĩa các cấu trúc dữ liệu (lược đồ) cho toàn bộ
ứng dụng chat, sử dụng thư viện Pydantic.

Việc định nghĩa các mô hình (Models) này đảm bảo rằng tất cả
dữ liệu được trao đổi giữa Server và Client đều tuân theo một
định dạng chuẩn, đồng thời cung cấp khả năng xác thực (validation)
và tuần tự hóa (serialization) một cách dễ dàng.
"""

from enum import Enum
from pydantic import BaseModel
import time

from configs import PM_PREFIX, SERVER_NAME


class MessageType(str, Enum):
    """
    Enum (liệt kê) các loại tin nhắn chính mà hệ thống
    có thể xử lý.
    """

    AUTH = "auth"  # Tin nhắn dùng cho việc xác thực
    CHAT = "chat"  # Tin nhắn chat thông thường
    RESPONSE = "response"  # Tin nhắn phản hồi từ server


class ChatMessage(BaseModel):
    """
    Mô hình Pydantic cho một tin nhắn chat.
    Đây chính là 'payload' (dữ liệu chính) khi `MessageType` là `CHAT`.
    """

    sender: str  # Tên người gửi
    content: str  # Nội dung tin nhắn
    timestamp: int  # Dấu thời gian (Unix timestamp)

    @property
    def encoded_bytes(self) -> bytes:
        """Chuyển đổi đối tượng tin nhắn thành chuỗi JSON và mã hóa sang bytes."""
        return self.model_dump_json().encode("utf-8")

    @property
    def message_string(self) -> str:
        """
        Trả về một chuỗi tin nhắn đã được định dạng đẹp, sẵn sàng
        để in ra màn hình console của client.
        """
        # Tin nhắn từ server thì không cần dấu thời gian
        if self.sender == SERVER_NAME:
            return f"[{self.sender}]: {self.content}"

        # Chuyển đổi timestamp thành định dạng con người có thể đọc
        human_readable_time = time.strftime(
            "%Y-%m-%d %H:%M:%S", time.localtime(self.timestamp)
        )

        return f"[{human_readable_time}] {self.sender}: {self.content}"

    @property
    def is_private(self) -> bool:
        """
        Kiểm tra xem tin nhắn này có phải là một tin nhắn riêng tư
        (được gửi bằng lệnh /pm) hay không.
        Một tin nhắn riêng tư hợp lệ phải có 3 phần:
        /pm <người_nhận> <nội_dung>
        """
        return (
            self.content.startswith(PM_PREFIX) and len(self.content.split(" ", 2)) == 3
        )


class GenericMessage(BaseModel):
    """
    Mô hình 'lồng' (wrapper) chung cho TẤT CẢ các tin nhắn
    được gửi qua mạng.
    Nó cho biết tin nhắn này thuộc loại nào (`type`) và
    dữ liệu của nó là gì (`payload`).
    """

    type: MessageType  # Loại tin nhắn (AUTH, CHAT, RESPONSE)
    payload: dict  # Dữ liệu thực sự (sẽ là một ChatMessage, AuthRequest, v.v.)

    @property
    def encoded_bytes(self) -> bytes:
        """Chuyển đổi toàn bộ đối tượng GenericMessage thành bytes."""
        return self.model_dump_json().encode("utf-8")


class AuthAction(str, Enum):
    """Enum các hành động xác thực."""

    LOGIN = "login"
    REGISTER = "register"


class AuthRequest(BaseModel):
    """
    Mô hình cho một yêu cầu xác thực.
    Đây là 'payload' khi `MessageType` là `AUTH`.
    """

    action: AuthAction  # Hành động là LOGIN hay REGISTER
    username: str
    password: str


class ServerResponseType(str, Enum):
    """Enum các loại phản hồi từ server."""

    SUCCESS = "success"  # Thành công
    ERROR = "error"  # Lỗi
    INFO = "info"  # Thông báo (ví dụ: user A vừa online)


class ServerResponse(BaseModel):
    """
    Mô hình cho một tin nhắn phản hồi từ Server.
    Đây là 'payload' khi `MessageType` là `RESPONSE`.
    """

    status: ServerResponseType  # Trạng thái (success, error, info)
    content: str  # Nội dung phản hồi

    @property
    def message_str(self) -> str:
        """Trả về chuỗi phản hồi đã được định dạng để in ra client."""
        return "[SERVER] " + self.content
