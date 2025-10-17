import socket
import threading

def receive_messages(client_socket):
    while True:
        try:
            message = client_socket.recv(1024).decode("utf-8")
            if message:
                if message.startswith("[SYSTEM]"):
                    print("\n📢 " + message[8:].strip())  
                else:
                    print("\n💬 " + message)
        except:
            print("❌ Mất kết nối tới server.")
            client_socket.close()
            break

def send_messages(client_socket):
    while True:
        try:
            message = input()
            if message.lower() == "exit":
                client_socket.close()
                break
            client_socket.send(message.encode("utf-8"))
        except:
            break

def main():
    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_ip = input("Nhập IP server: ")  
    try:
        client.connect((server_ip, 5555))
    except:
        print("❌ Không thể kết nối tới server.")
        return

    # Gửi tên
    response = client.recv(1024).decode("utf-8")
    print(response)
    name = input("Tên: ")
    client.send(name.encode("utf-8"))

    # Tạo luồng
    recv_thread = threading.Thread(target=receive_messages, args=(client,))
    send_thread = threading.Thread(target=send_messages, args=(client,))
    recv_thread.start()
    send_thread.start()

if __name__ == "__main__":
    main()
