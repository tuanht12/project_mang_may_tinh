"""\
Module này định nghĩa lớp `ChatClient`, một lớp (class) đơn giản
để đóng gói (wrap) đối tượng socket của client cùng với tên người dùng (username)
của họ sau khi đã xác thực.

Việc sử dụng lớp này giúp cho việc quản lý danh sách client ở phía server
trở nên rõ ràng và có tổ chức hơn, thay vì chỉ lưu trữ các đối tượng socket.
"""

from socket import socket


class ChatClient:
    """
    Đại diện cho một client đã kết nối, bao gồm socket và tên người dùng.

    Attributes:
        socket (socket): Đối tượng socket của client.
        username (str): Tên người dùng của client (được gán sau khi xác thực).
    """

    def __init__(self, socket: socket):
        """
        Khởi tạo một đối tượng ChatClient mới.

        Args:
            socket (socket): Đối tượng socket đang hoạt động của client.
        """
        self.socket = socket
        self.username: str = None  # Sẽ được gán sau khi đăng nhập thành công

    @property
    def peer_name(self):
        """
        Trả về địa chỉ (IP, port) của client.
        Đây là một thuộc tính (property) chỉ đọc.
        """
        try:
            return self.socket.getpeername()
        except OSError:
            return "N/A (đã ngắt kết nối)"

    def __eq__(self, value):
        """
        Kiểm tra xem hai đối tượng ChatClient có bằng nhau không.
        Chúng được coi là bằng nhau nếu chúng có cùng một đối tượng socket.
        """
        if not isinstance(value, ChatClient):
            return False
        return self.socket == value.socket
