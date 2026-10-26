"""
Jonaki for Linux - Single-Instance Coordinator & IPC Protocol
Unix Domain Socket Server & Client for command delegation (/new, /current, /add, /seek, etc.).
"""

import os
import json
import socket
import threading
from typing import Callable, Optional, Dict, Any


def get_default_ipc_socket_path() -> str:
    runtime_dir = os.environ.get("XDG_RUNTIME_DIR")
    if not runtime_dir or not os.path.isdir(runtime_dir):
        uid = os.getuid()
        runtime_dir = f"/tmp/jonaki_{uid}"
        os.makedirs(runtime_dir, exist_ok=True)
    return os.path.join(runtime_dir, "jonaki_ipc.sock")


class IPCServer:
    """
    Listens for commands from secondary player instances or CLI scripts.
    Dispatches parsed JSON actions to the host application controller.
    """
    def __init__(self, command_handler: Callable[[Dict[str, Any]], Dict[str, Any]], socket_path: Optional[str] = None):
        self.socket_path = socket_path or get_default_ipc_socket_path()
        self.command_handler = command_handler
        self._server_socket: Optional[socket.socket] = None
        self._is_running = False
        self._owns_socket = False
        self._thread: Optional[threading.Thread] = None

    def start(self) -> bool:
        # Check if already bound
        if os.path.exists(self.socket_path):
            try:
                # Test connection
                test_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                test_sock.connect(self.socket_path)
                test_sock.close()
                # Server is already alive!
                return False
            except (socket.error, OSError):
                # Stale socket file
                try:
                    os.unlink(self.socket_path)
                except OSError:
                    pass

        try:
            self._server_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self._server_socket.bind(self.socket_path)
            self._owns_socket = True
            self._server_socket.listen(10)
            self._is_running = True
            self._thread = threading.Thread(target=self._listen_loop, daemon=True, name="IPCServer")
            self._thread.start()
            return True
        except Exception as e:
            print(f"[IPCServer] Failed to bind to {self.socket_path}: {e}")
            return False

    def _listen_loop(self) -> None:
        while self._is_running and self._server_socket:
            try:
                client_sock, _ = self._server_socket.accept()
                threading.Thread(target=self._handle_client, args=(client_sock,), daemon=True).start()
            except OSError:
                break

    def _handle_client(self, client_sock: socket.socket) -> None:
        with client_sock:
            try:
                data = client_sock.recv(65536)
                if not data:
                    return
                message = json.loads(data.decode("utf-8"))
                response = self.command_handler(message)
                client_sock.sendall(json.dumps(response).encode("utf-8"))
            except Exception as e:
                try:
                    client_sock.sendall(json.dumps({"status": "error", "message": str(e)}).encode("utf-8"))
                except OSError:
                    pass

    def stop(self) -> None:
        self._is_running = False
        if self._server_socket:
            try:
                self._server_socket.close()
            except OSError:
                pass
            self._server_socket = None
        if self._owns_socket and os.path.exists(self.socket_path):
            try:
                os.unlink(self.socket_path)
            except OSError:
                pass
            self._owns_socket = False


class IPCClient:
    """
    Sends commands to the active primary Jonaki instance.
    """
    def __init__(self, socket_path: Optional[str] = None):
        self.socket_path = socket_path or get_default_ipc_socket_path()

    def is_server_running(self) -> bool:
        if not os.path.exists(self.socket_path):
            return False
        try:
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            s.settimeout(0.5)
            s.connect(self.socket_path)
            s.close()
            return True
        except (socket.error, OSError):
            return False

    def send_command(self, payload: Dict[str, Any], timeout: float = 2.0) -> Optional[Dict[str, Any]]:
        try:
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            s.settimeout(timeout)
            s.connect(self.socket_path)
            s.sendall(json.dumps(payload).encode("utf-8"))
            raw = s.recv(65536)
            s.close()
            if raw:
                return json.loads(raw.decode("utf-8"))
            return None
        except Exception as e:
            print(f"[IPCClient] Command send failed: {e}")
            return None
