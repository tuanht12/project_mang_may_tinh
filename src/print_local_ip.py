import socket


def get_local_ip():
    """
    Tries to determine the local IP address of the machine.
    Returns '127.0.0.1' on failure.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # This doesn't send any data, it just opens a socket to determine the route.
        s.connect(("8.8.8.8", 1))
        IP = s.getsockname()[0]
    except Exception:
        IP = "127.0.0.1"  # Fallback to loopback address
    finally:
        s.close()
    return IP


if __name__ == "__main__":
    print("Local IP Address:", get_local_ip())
    print("Use this IP in the 'configs.py' file for both server and client.")
