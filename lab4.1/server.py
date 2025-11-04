import socket
import threading

HOST = "localhost"
PORT = 2025

clients: set[socket.socket] = set()
clients_lock = threading.Lock()

def broadcast(message: bytes) -> None:
    to_remove: list[socket.socket] = []
    with clients_lock:
        for c in list(clients):
            try:
                c.sendall(message)
            except Exception:
                to_remove.append(c)
        for c in to_remove:
            try:
                clients.remove(c)
            except KeyError:
                pass
            try:
                c.close()
            except Exception:
                pass


def handle_client(conn: socket.socket, addr: tuple[str, int]) -> None:
    with conn:
        print(f"Connected by {addr}")
        with clients_lock:
            clients.add(conn)
        try:
            while True:
                data = conn.recv(1024)
                if not data:
                    break
                broadcast(data)
        except ConnectionError:
            pass
        finally:
            with clients_lock:
                if conn in clients:
                    clients.remove(conn)
            print(f"Disconnected {addr}")


def main() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((HOST, PORT))
        s.listen()
        print(f"Server listening on {HOST}:{PORT}")
        while True:
            conn, addr = s.accept()
            t = threading.Thread(target=handle_client, args=(conn, addr), daemon=True)
            t.start()


if __name__ == "__main__":
    main()