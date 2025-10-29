"""\
Đây là một script tiện ích đơn giản để giúp người dùng
tìm ra địa chỉ IP nội bộ (IPv4) của máy tính.

Địa chỉ IP này là địa chỉ mà máy chủ (Server) sẽ lắng nghe
và các máy khách (Client) khác trong cùng mạng LAN sẽ sử dụng
để kết nối đến.
"""

import socket


def get_local_ip():
    """
    Cố gắng xác định địa chỉ IP cục bộ của máy.
    Trả về '127.0.0.1' nếu thất bại.

    Hàm này hoạt động bằng cách tạo một kết nối (ảo) đến một máy chủ
    công cộng (như DNS của Google). Hệ điều hành sẽ tự động
    chọn giao diện mạng (network interface) phù hợp để đi ra ngoài,
    và từ đó ta có thể lấy được địa chỉ IP cục bộ của giao diện đó.

    Returns:
        str: Địa chỉ IPV4 cục bộ của máy.
    """
    # Tạo một socket UDP (SOCK_DGRAM)
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # Không cần gửi dữ liệu, chỉ cần gọi connect()
        # đến một địa chỉ công cộng.
        # Port 1 là một port tùy chọn, không quan trọng.
        s.connect(("8.8.8.8", 1))
        # Lấy địa chỉ IP mà socket đang sử dụng
        IP = s.getsockname()[0]
    except Exception:
        # Nếu có lỗi (ví dụ: không có mạng), trả về địa chỉ loopback
        IP = "127.0.0.1"
    finally:
        # Luôn đóng socket sau khi hoàn tất
        s.close()
    return IP


if __name__ == "__main__":
    """
    Điểm vào chính khi chạy file này trực tiếp.
    """
    local_ip = get_local_ip()
    print(f"Địa chỉ IP cục bộ của bạn là: {local_ip}")
    print("Hãy sử dụng địa chỉ IP này trong file 'configs.py'")
    print("cho cả Server và Client khi chạy trong mạng LAN.")
