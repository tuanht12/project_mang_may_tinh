"""\
Module này chứa tất cả các biến cấu hình, hằng số và các cài đặt
được chia sẻ giữa cả Server và Client.

Việc tập trung tất cả các cấu hình vào một file giúp cho việc
quản lý, thay đổi và bảo trì ứng dụng trở nên dễ dàng hơn.
"""

from pathlib import Path

# --- Cài đặt kết nối ---
# Thay đổi '127.0.0.1' thành địa chỉ IPV4 của máy chạy server.
# Dùng print_local_ip.py để tìm IP này.
SERVER_HOST = "127.0.0.1"  # Địa chỉ IP của server
SERVER_PORT = 65432  # Cổng mà server sẽ lắng nghe
DEFAULT_BUFFER_SIZE = 1024  # Kích thước bộ đệm (bytes) cho mỗi lần nhận dữ liệu

# --- Cài đặt phía Server ---
# Lấy đường dẫn thư mục cha của thư mục chứa file này (dự án)
CUR_DIR = Path(__file__).parent.parent.resolve()
DB_PATH = CUR_DIR / "db"  # Đường dẫn đến thư mục cơ sở dữ liệu
USERS_CSV = DB_PATH / "users.csv"  # Đường dẫn đến file CSV lưu trữ dữ liệu người dùng
SERVER_NAME = "SERVER"  # Tên định danh cho các tin nhắn từ server

# --- Tiền tố lệnh ---
PM_PREFIX = "/pm"  # Tiền tố cho tin nhắn riêng tư
QUIT_COMMAND = "/quit"  # Lệnh để thoát chat
SHOW_USERS_COMMAND = "/users"  # Lệnh để xem danh sách người dùng


def get_welcome_message(username: str) -> str:
    """
    Tạo và trả về một chuỗi tin nhắn chào mừng đã được định dạng
    cho người dùng mới đăng nhập.

    Args:
        username (str): Tên của người dùng.

    Returns:
        str: Tin nhắn chào mừng.
    """
    # Sử dụng f-string với 3 dấu nháy kép để tạo chuỗi đa dòng
    msg = f"""Chào mừng {username} đã đến với phòng chat!

    Hướng dẫn:
    - Gõ tin nhắn và nhấn Enter để gửi.
    - Gõ {SHOW_USERS_COMMAND} để xem danh sách người dùng đang hoạt động.
    - Dùng {PM_PREFIX} <username> <tin nhắn> để gửi tin nhắn riêng.
    - Gõ {QUIT_COMMAND} để thoát khỏi phòng chat."""

    # Dọn dẹp các ký tự tab hoặc khoảng trắng thừa để hiển thị đẹp hơn
    return msg.replace("\t", " ").replace("    ", " ").strip()
