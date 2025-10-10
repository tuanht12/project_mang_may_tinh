from typing import List, Dict, Set, Optional
from configs import DEFAULT_BUFFER_SIZE, SERVER_PORT, SERVER_HOST
import socket
import threading
import os
import time
import re

from schemas import ChatMessage
from utils import print_message_in_bytes

# -------------------------
# Global state (no OOP)
# -------------------------
clients: List[socket.socket] = []
clients_lock = threading.Lock()
state_lock = threading.RLock()

# nickname <-> socket mappings
name_to_sock: Dict[str, socket.socket] = {}
sock_to_name: Dict[socket.socket, str] = {}

# room name -> set of sockets
rooms: Dict[str, Set[socket.socket]] = {"lobby": set()}

# socket -> current room
sock_room: Dict[socket.socket, str] = {}

LOG_DIR = "logs"

# -------------------------
# Utilities (server side)
# -------------------------
def ensure_log_dir():
    os.makedirs(LOG_DIR, exist_ok=True)

def safe_filename(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_\-]", "_", name)

def dm_log_filename(a: str, b: str) -> str:
    a1, b1 = sorted([a, b], key=str.lower)
    return os.path.join(LOG_DIR, f"dm__{safe_filename(a1)}__{safe_filename(b1)}.log")

def room_log_filename(room: str) -> str:
    return os.path.join(LOG_DIR, f"room__{safe_filename(room)}.log")

def append_history_line(path: str, line: str):
    ensure_log_dir()
    with open(path, "a", encoding="utf-8") as f:
        f.write(line.rstrip("\n") + "\n")

def tail_history(path: str, n: int = 20) -> str:
    if not os.path.exists(path):
        return "(no history)"
    with open(path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    last = "".join(lines[-n:])
    return last or "(no history)"

def now_ts() -> int:
    return int(time.time())

def system_message(content: str) -> ChatMessage:
    return ChatMessage(sender="*system*", content=content, timestamp=now_ts())

def send_bytes(sock: socket.socket, b: bytes):
    try:
        sock.sendall(b)
    except Exception:
        try:
            sock.close()
        finally:
            pass

def send_chat(sock: socket.socket, msg: ChatMessage):
    send_bytes(sock, msg.encoded_bytes)

def broadcast_room(room: str, msg: ChatMessage, exclude: Optional[socket.socket] = None):
    # iterate over copy to avoid mutation issues
    targets = list(rooms.get(room, set()))
    for s in targets:
        if s is exclude:
            continue
        send_chat(s, msg)

def register_if_needed(sock: socket.socket, sender: str):
    # gắn nickname lần đầu & cho vào lobby
    with state_lock:
        if sock not in sock_to_name:
            base = sender or "guest"
            name = base
            i = 1
            while name in name_to_sock and name_to_sock[name] is not sock:
                i += 1
                name = f"{base}{i}"

            sock_to_name[sock] = name
            name_to_sock[name] = sock

            rooms.setdefault("lobby", set()).add(sock)
            sock_room[sock] = "lobby"

            broadcast_room("lobby", system_message(f"{name} joined lobby"))

def leave_current_room(sock: socket.socket):
    with state_lock:
        room = sock_room.get(sock)
        if room:
            if sock in rooms.get(room, set()):
                rooms[room].discard(sock)
                who = sock_to_name.get(sock, "someone")
                broadcast_room(room, system_message(f"{who} left {room}"))
        sock_room[sock] = ""

def join_room(sock: socket.socket, room: str):
    with state_lock:
        leave_current_room(sock)
        rooms.setdefault(room, set()).add(sock)
        sock_room[sock] = room
        who = sock_to_name.get(sock, "someone")
        broadcast_room(room, system_message(f"{who} joined {room}"))

def handle_command(sock: socket.socket, msg: ChatMessage) -> bool:
    """
    Trả về True nếu là lệnh và đã xử lý; False nếu không phải lệnh.
    """
    text = (msg.content or "").strip()
    if not text.startswith("/"):
        return False

    parts = text.split()
    cmd = parts[0].lower()

    # /help
    if cmd in ("/help", "/h", "/?"):
        help_text = (
            "Commands:\n"
            "/help - this help\n"
            "/rooms - list rooms\n"
            "/users - list users in current room\n"
            "/create <room> - create a room and join\n"
            "/join <room> - join a room\n"
            "/leave - leave current room to lobby\n"
            "/pm <user> <message> - send private message\n"
            "/history [N] - last N lines for current room (default 20)\n"
            "/history @user [N] - last N lines for DM with @user\n"
        )
        send_chat(sock, system_message(help_text))
        return True

    # /rooms
    if cmd == "/rooms":
        with state_lock:
            names = sorted(rooms.keys())
        send_chat(sock, system_message("Rooms: " + ", ".join(names)))
        return True

    # /users
    if cmd == "/users":
        with state_lock:
            room = sock_room.get(sock, "lobby")
            names = [sock_to_name.get(s, "?") for s in rooms.get(room, set())]
        send_chat(sock, system_message(f"Users in {room}: " + ", ".join(sorted(names))))
        return True

    # /create <room>
    if cmd == "/create" and len(parts) >= 2:
        room = parts[1]
        join_room(sock, room)
        send_chat(sock, system_message(f"Created and joined room {room}"))
        return True

    # /join <room>
    if cmd == "/join" and len(parts) >= 2:
        room = parts[1]
        join_room(sock, room)
        send_chat(sock, system_message(f"Joined room {room}"))
        return True

    # /leave
    if cmd == "/leave":
        join_room(sock, "lobby")
        return True

    # /pm <user> <message...>
    if cmd in ("/pm", "/w") and len(parts) >= 3:
        target_name = parts[1].lstrip("@")
        with state_lock:
            target = name_to_sock.get(target_name)
            sender = sock_to_name.get(sock, msg.sender)
        if not target:
            send_chat(sock, system_message(f"User @{target_name} not found"))
            return True
        dm_text = " ".join(parts[2:])
        dm = ChatMessage(sender=sender, content=f"(PM to @{target_name}) {dm_text}", timestamp=now_ts())
        # gửi cho người nhận và echo lại cho người gửi
        send_chat(target, dm)
        send_chat(sock, dm)
        append_history_line(dm_log_filename(sender, target_name), f"{dm.timestamp}\t{sender}\t{dm_text}")
        return True

    # /history...
    if cmd == "/history":
        with state_lock:
            room = sock_room.get(sock, "lobby")
            sender = sock_to_name.get(sock, msg.sender)

        # /history @user N
        if len(parts) >= 2 and parts[1].startswith("@"):
            target_name = parts[1].lstrip("@")
            n = int(parts[2]) if len(parts) >= 3 and parts[2].isdigit() else 20
            path = dm_log_filename(sender, target_name)
            out = tail_history(path, n)
            send_chat(sock, system_message(f"DM history @{target_name} (last {n}):\n{out}"))
            return True
        # /history N
        n = int(parts[1]) if len(parts) >= 2 and parts[1].isdigit() else 20
        path = room_log_filename(room)
        out = tail_history(path, n)
        send_chat(sock, system_message(f"Room history {room} (last {n}):\n{out}"))
        return True

    # unknown
    send_chat(sock, system_message("Unknown command. Type /help"))
    return True

def create_server_socket():
    """Create and return a server socket listening on SERVER_HOST and SERVER_PORT"""
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind((SERVER_HOST, SERVER_PORT))
    server_socket.listen()
    print(f"[server] listening on {SERVER_HOST}:{SERVER_PORT}")
    ensure_log_dir()
    return server_socket

def handle_client(client_socket: socket.socket):
    try:
        while True:
            try:
                message_bytes = client_socket.recv(DEFAULT_BUFFER_SIZE)
            except ConnectionResetError:
                break
            if not message_bytes:
                break

            # giữ behavior cũ: log ra console theo utils
            print_message_in_bytes(message_bytes)

            # parse JSON -> ChatMessage
            try:
                msg = ChatMessage.model_validate_json(message_bytes.decode("utf-8"))
            except Exception:
                send_chat(client_socket, system_message("Invalid message format"))
                continue

            # đăng ký nickname + vào lobby lần đầu
            register_if_needed(client_socket, msg.sender)

            # nếu là lệnh -> xử lý rồi continue
            if handle_command(client_socket, msg):
                continue

            # broadcast message thường theo room hiện tại
            with state_lock:
                room = sock_room.get(client_socket, "lobby")
            broadcast_room(room, msg)

            # ghi log room
            line = f"{msg.timestamp}\t{msg.sender}\t{msg.content}"
            append_history_line(room_log_filename(room), line)

    finally:
        # cleanup
        with clients_lock:
            if client_socket in clients:
                clients.remove(client_socket)

        with state_lock:
            name = sock_to_name.pop(client_socket, None)
            if name and name_to_sock.get(name) is client_socket:
                del name_to_sock[name]
            room = sock_room.pop(client_socket, "")
            if room and client_socket in rooms.get(room, set()):
                rooms[room].discard(client_socket)

        if room:
            broadcast_room(room, system_message(f"{name or 'someone'} disconnected"))
        try:
            client_socket.close()
        except Exception:
            pass

if __name__ == "__main__":
    server_socket = create_server_socket()
    while True:
        client_socket, addr = server_socket.accept()
        with clients_lock:
            clients.append(client_socket)
        thread = threading.Thread(target=handle_client, args=(client_socket,))
        thread.daemon = True
        thread.start()
tail_history