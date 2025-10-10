# chat_client.py — auto-reconnect + auto-register-to-lobby (no NDJSON)
import socket
import threading
import time
from typing import Optional
from configs import SERVER_HOST, SERVER_PORT, DEFAULT_BUFFER_SIZE
from schemas import ChatMessage
from utils import print_message_in_bytes

# ---- Global (non-OOP) ----
sock_lock = threading.Lock()
reconnect_lock = threading.Lock()
current_socket: Optional[socket.socket] = None
stop_flag = False

NICKNAME = ""
LAST_ROOM = ""  # nhớ phòng gần nhất khi user dùng /join hoặc /create

# ---- Helpers ----
def connect_once() -> socket.socket:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect((SERVER_HOST, SERVER_PORT))
    return s

def set_socket(s: Optional[socket.socket]):
    global current_socket
    with sock_lock:
        current_socket = s

def get_socket() -> Optional[socket.socket]:
    with sock_lock:
        return current_socket

def send_chat_raw(sock: socket.socket, content: str):
    # framing cũ: 1 message = 1 lần sendall (không newline)
    msg = ChatMessage(sender=NICKNAME, content=content, timestamp=int(time.time()))
    sock.sendall(msg.encoded_bytes)

def maybe_capture_last_room(user_input: str):
    global LAST_ROOM
    parts = user_input.strip().split()
    if len(parts) < 2:
        return
    cmd = parts[0].lower()
    if cmd not in ("/join", "/create"):
        return
    room = parts[1]
    if room.lower() == "room" and len(parts) >= 3:
        room = parts[2]
    if room:
        LAST_ROOM = room

def handshake_after_connect(sock: socket.socket):
    """
    Gửi 1 lệnh nhẹ để server 'register + join lobby' ngay,
    sau đó (nếu có) vào lại LAST_ROOM.
    """
    try:
        # 1) bắt buộc gửi /users để kích hoạt register_if_needed() ở server
        send_chat_raw(sock, "/users")
        # Nghỉ 50ms để giảm khả năng 2 system message dính vào 1 recv
        time.sleep(0.05)

        # 2) nếu có phòng trước đó -> join lại
        if LAST_ROOM and LAST_ROOM.lower() != "lobby":
            send_chat_raw(sock, f"/join {LAST_ROOM}")
    except Exception:
        pass

def reconnect_loop():
    # đảm bảo chỉ 1 thread reconnect tại 1 thời điểm
    if not reconnect_lock.acquire(blocking=False):
        while not stop_flag and get_socket() is None:
            time.sleep(0.2)
        return
    try:
        delay = 1
        while not stop_flag:
            try:
                print(f"[client] Reconnecting to {SERVER_HOST}:{SERVER_PORT} ...")
                s = connect_once()
                set_socket(s)
                print("[client] Reconnected.")
                handshake_after_connect(s)   # <— thêm handshake sau reconnect
                return
            except Exception:
                print(f"[client] Reconnect failed. Retry in {delay}s ...")
                time.sleep(delay)
                delay = 2 if delay == 1 else (3 if delay == 2 else 5)
    finally:
        reconnect_lock.release()

# ---- Threads ----
# --- thêm helper ở phía trên file (bất kỳ sau imports) ---
def split_concatenated_json_bytes(b: bytes):
    """
    Tách 1 chunk bytes có thể chứa N object JSON dính liền thành list[bytes].
    Duyệt theo depth ngoặc nhọn, bỏ qua ngoặc trong string.
    """
    s = b.decode("utf-8", errors="ignore")
    out = []
    depth = 0
    in_str = False
    esc = False
    start = -1
    for i, ch in enumerate(s):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        else:
            if ch == '"':
                in_str = True
            elif ch == "{":
                if depth == 0:
                    start = i
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0 and start != -1:
                    out.append(s[start:i+1].encode("utf-8"))
                    start = -1
    # nếu không tách được gì, trả nguyên chunk để caller tự xử lý
    return out or [b]

# --- thay toàn bộ hàm receive_loop bằng bản dưới ---
def receive_loop():
    """
    Luồng nhận: chỉ coi là 'lost connection' khi socket đóng / lỗi I/O.
    Lỗi parse JSON thì cố tách/chấp nhận bỏ qua, KHÔNG reconnect.
    """
    while not stop_flag:
        s = get_socket()
        if s is None:
            time.sleep(0.2)
            continue
        try:
            data = s.recv(DEFAULT_BUFFER_SIZE)
            if not data:
                # server đóng thật
                raise ConnectionError("socket closed")

            # Có thể chứa nhiều JSON dính nhau -> tách rồi in từng cái
            for piece in split_concatenated_json_bytes(data):
                try:
                    print_message_in_bytes(piece)
                except Exception as e:
                    # cảnh báo nhẹ rồi bỏ qua message lỗi, không coi là rớt mạng
                    print(f"[client] WARN: bad message chunk ignored ({e})")
        except (ConnectionError, OSError):
            # Chỉ khi lỗi network/socket mới reconnect
            set_socket(None)
            print("[client] Lost connection.")
            reconnect_loop()

def send_loop():
    while not stop_flag:
        try:
            content = input("> ")
        except EOFError:
            break
        if stop_flag:
            break
        if not content:
            continue

        maybe_capture_last_room(content)

        sent = False
        for attempt in (1, 2):  # thử lại 1 lần sau khi reconnect
            s = get_socket()
            if s is None:
                reconnect_loop()
                s = get_socket()
                if s is None:
                    break
            try:
                send_chat_raw(s, content)
                sent = True
                break
            except Exception:
                set_socket(None)
                if attempt == 1:
                    print("[client] Send failed. Reconnecting ...")
                    reconnect_loop()
        if not sent:
            print("[client] Failed to send. Please try again.")

def start_client():
    global NICKNAME
    # kết nối ban đầu (nếu fail vẫn cho vào vòng reconnect)
    try:
        s = connect_once()
        set_socket(s)
    except ConnectionRefusedError:
        print("Cannot connect to server. Make sure the server is running.")
        set_socket(None)

    NICKNAME = input("Choose your nickname: ").strip() or "guest"

    # nếu đã có socket ngay từ đầu -> handshake để vào lobby luôn
    s0 = get_socket()
    if s0 is not None:
        handshake_after_connect(s0)

    t_recv = threading.Thread(target=receive_loop, daemon=True)
    t_recv.start()

    try:
        send_loop()
    finally:
        global stop_flag
        stop_flag = True
        s = get_socket()
        if s:
            try:
                s.close()
            except Exception:
                pass
        time.sleep(0.2)

if __name__ == "__main__":
    start_client()
