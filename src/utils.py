"""
Module này chứa các hàm tiện ích được chia sẻ bởi cả Server và Client.
Các chức năng bao gồm:
- Tương tác với cơ sở dữ liệu người dùng (file CSV).
- Đóng socket một cách an toàn.
- Các hàm giao diện dòng lệnh (CLI) để lấy thông tin từ người dùng.
"""

import getpass
import socket

import pandas as pd

from configs import QUIT_COMMAND
from schemas import AuthAction

# --- Các hàm xử lý Cơ sở dữ liệu (Pandas) ---


def add_new_user_to_db(
    current_df: pd.DataFrame, username: str, password: str
) -> pd.DataFrame:
    """
    Thêm một người dùng mới vào DataFrame và trả về DataFrame đã cập nhật.
    Không lưu trực tiếp xuống file CSV, chỉ thao tác trên bộ nhớ.

    Args:
        current_df (pd.DataFrame): DataFrame hiện tại chứa dữ liệu người dùng.
        username (str): Tên người dùng mới.
        password (str): Mật khẩu của người dùng mới.

    Returns:
        pd.DataFrame: DataFrame đã được cập nhật với người dùng mới.
    """
    if username in current_df["username"].values:
        return current_df  # Username already exists
    new_user = pd.DataFrame({"username": [username], "password": [password]})
    current_df = pd.concat([current_df, new_user], ignore_index=True)
    return current_df


def verify_user_credentials(df: pd.DataFrame, username: str, password: str) -> bool:
    """
    Xác minh thông tin đăng nhập của người dùng dựa trên DataFrame.

    Args:
        df (pd.DataFrame): DataFrame chứa dữ liệu người dùng.
        username (str): Tên người dùng cần kiểm tra.
        password (str): Mật khẩu cần kiểm tra.

    Returns:
        bool: True nếu thông tin chính xác, False nếu ngược lại.
    """
    # Tìm dòng (row) có username khớp
    user_row = df[df["username"] == username]
    # Nếu không tìm thấy (DataFrame rỗng)
    if user_row.empty:
        return False
    # Lấy mật khẩu đã lưu và so sánh
    current_password = str(user_row["password"].iloc[0])
    return current_password == password


# --- Hàm xử lý Mạng (Socket) ---


def close_socket(sock: socket.socket):
    """
    Đóng một đối tượng socket một cách an toàn và triệt để.
    Hàm này xử lý các trường hợp socket đã bị đóng hoặc chưa kết nối.

    Args:
        sock (socket.socket): Đối tượng socket cần đóng.
    """
    # fileno() == -1 có nghĩa là socket đã bị đóng
    if sock.fileno() == -1:
        return
    try:
        # Thông báo cho cả hai chiều (đọc và ghi) rằng kết nối sắp đóng
        sock.shutdown(socket.SHUT_RDWR)
    except OSError:
        # Bỏ qua lỗi nếu socket đã bị đóng hoặc chưa kết nối
        pass
    finally:
        # Luôn gọi close() để giải phóng tài nguyên
        sock.close()


# --- Các hàm Giao diện Người dùng (CLI) ---


def request_user_login_register() -> AuthAction:
    """
    Hiển thị menu cho người dùng chọn Đăng nhập hoặc Đăng ký.

    Returns:
        AuthAction: Hành động người dùng đã chọn (LOGIN hoặc REGISTER),
                    hoặc None nếu người dùng muốn thoát.
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
    Yêu cầu người dùng nhập tên người dùng và mật khẩu.
    Sử dụng getpass để ẩn mật khẩu khi gõ.

    Returns:
        tuple[str, str]: (username, password).
                         Trả về (None, None) nếu người dùng nhập rỗng.
    """
    username = input("Enter username: ").strip()
    # getpass.getpass() tự động ẩn mật khẩu khi người dùng gõ
    password = getpass.getpass("Enter password: ")
    # Kiểm tra xem người dùng có nhập rỗng không
    if not username or not password:
        print("Username and password cannot be empty.")
        return None, None

    return username, password
