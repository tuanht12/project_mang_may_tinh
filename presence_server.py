import socket
import threading

clients = {}  # {socket: username}


def broadcast(message, sender=None):
    for client in clients:
        if client != sender:
            try:
                client.send(message.encode("utf-8"))
            except:
                client.close()
                del clients[client]


def handle_client(client_socket):
    try:
        # Nhận tên người dùng khi mới kết nối
        client_socket.send("Nhập tên của bạn: ".encode("utf-8"))
        username = client_socket.recv(1024).decode("utf-8").strip()
        clients[client_socket] = username

        print(f"[KẾT NỐI] {username} đã tham gia.")
        broadcast(f"🔵 {username} đã online", client_socket)
        client_socket.send(f"Bạn đã kết nối thành công. Nhập /online để xem ai đang online.".encode("utf-8"))

        while True:
            msg = client_socket.recv(1024).decode("utf-8")
            if not msg:
                break

            if msg.strip() == "/online":
                online_users = ", ".join(clients.values())
                client_socket.send(f"👥 Đang online: {online_users}".encode("utf-8"))
            else:
                broadcast(f"{username}: {msg}", client_socket)

    except:
        pass
    finally:
        username = clients.get(client_socket, "Người dùng")
        print(f"[NGẮT KẾT NỐI] {username}")
        broadcast(f"🔴 {username} đã offline", client_socket)
        client_socket.close()
        if client_socket in clients:
            del clients[client_socket]


def start_server():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("0.0.0.0", 5555))
    server.listen(5)
    print("[SERVER] Đang chạy...")

    while True:
        client_socket, _ = server.accept()
        thread = threading.Thread(target=handle_client, args=(client_socket,))
        thread.start()

if __name__ == "__main__":
    start_server()
