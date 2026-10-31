"""
Jonaki for Linux - Single-Instance Coordinator & IPC Protocol
Unix Domain Socket Server & Client for command delegation (/new, /current, /add, /seek, etc.).
"""

import os
import json
import socket
import struct
import threading
import time
from typing import Callable, Optional, Dict, Any


import fcntl
import gi
gi.require_version('GLib', '2.0')
from gi.repository import GLib


def get_default_ipc_socket_path() -> str:
    runtime_dir = os.environ.get("XDG_RUNTIME_DIR")
    if not runtime_dir or not os.path.isdir(runtime_dir):
        uid = os.getuid()
        runtime_dir = f"/tmp/jonaki_{uid}"
        os.makedirs(runtime_dir, mode=0o700, exist_ok=True)
        try:
            stat_info = os.lstat(runtime_dir)
            if os.path.islink(runtime_dir) or stat_info.st_uid != uid:
                import tempfile
                runtime_dir = tempfile.mkdtemp(prefix=f"jonaki_{uid}_")
            elif (stat_info.st_mode & 0o777) != 0o700:
                os.chmod(runtime_dir, 0o700)
        except Exception:
            pass
    return os.path.join(runtime_dir, "jonaki_ipc.sock")


def _send_msg(sock: socket.socket, data: bytes) -> None:
    sock.sendall(struct.pack(">I", len(data)) + data)


def _recv_all(sock: socket.socket, n: int) -> Optional[bytes]:
    data = bytearray()
    while len(data) < n:
        packet = sock.recv(min(n - len(data), 65536))
        if not packet:
            return None
        data.extend(packet)
    return bytes(data)


def _recv_msg(sock: socket.socket) -> Optional[bytes]:
    header = _recv_all(sock, 4)
    if not header:
        return None
    if header.startswith(b"{") or header.startswith(b"["):
        chunks = [header]
        total = len(header)
        max_size = 2 * 1024 * 1024
        while total < max_size:
            chunk = sock.recv(65536)
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
        return b"".join(chunks)
    (length,) = struct.unpack(">I", header)
    if length > 32 * 1024 * 1024:
        return None
    return _recv_all(sock, length)


class IPCServer:
    """
    Listens for commands from secondary player instances or CLI scripts.
    Dispatches parsed JSON actions to the host application controller.
    """
    def __init__(self, command_handler: Callable[[Dict[str, Any]], Dict[str, Any]], socket_path: Optional[str] = None):
        self.socket_path = socket_path or get_default_ipc_socket_path()
        self.lock_path = self.socket_path + ".lock"
        self._lock_file: Optional[Any] = None
        self.command_handler = command_handler
        self._server_socket: Optional[socket.socket] = None
        self._is_running = False
        self._owns_socket = False
        self._thread: Optional[threading.Thread] = None
        self._concurrency_semaphore = threading.BoundedSemaphore(10)

    def start(self) -> bool:
        # Acquire advisory file lock to eliminate TOCTOU races between concurrent instances
        try:
            self._lock_file = open(self.lock_path, "w")
            fcntl.flock(self._lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (BlockingIOError, OSError):
            if self._lock_file:
                try:
                    self._lock_file.close()
                except Exception:
                    pass
                self._lock_file = None
            return False

        # Check if already bound
        if os.path.exists(self.socket_path):
            try:
                # Test connection
                with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as test_sock:
                    test_sock.settimeout(0.5)
                    test_sock.connect(self.socket_path)
                # Server is already alive!
                self._release_lock()
                return False
            except (socket.error, OSError):
                # Stale socket file
                try:
                    os.unlink(self.socket_path)
                except OSError:
                    pass

        try:
            self._server_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            old_umask = os.umask(0o077)
            try:
                self._server_socket.bind(self.socket_path)
            finally:
                os.umask(old_umask)
            try:
                os.chmod(self.socket_path, 0o600)
            except Exception:
                pass
            self._owns_socket = True
            self._server_socket.listen(128)
            self._is_running = True
            self._thread = threading.Thread(target=self._listen_loop, daemon=True, name="IPCServer")
            self._thread.start()
            return True
        except Exception as e:
            print(f"[IPCServer] Failed to bind to {self.socket_path}: {e}")
            if self._server_socket:
                try:
                    self._server_socket.close()
                except OSError:
                    pass
                self._server_socket = None
            self._release_lock()
            return False

    def _release_lock(self) -> None:
        if self._lock_file:
            try:
                fcntl.flock(self._lock_file, fcntl.LOCK_UN)
                self._lock_file.close()
            except Exception:
                pass
            self._lock_file = None
        # Note: Do not unlink self.lock_path! Retaining the lock file on disk preserves
        # advisory POSIX flock mutual exclusion across concurrent and subsequent processes.

    def _listen_loop(self) -> None:
        while self._is_running and self._server_socket:
            try:
                client_sock, _ = self._server_socket.accept()
                if not self._concurrency_semaphore.acquire(blocking=False):
                    try:
                        _send_msg(client_sock, json.dumps({"status": "error", "message": "Server busy"}).encode("utf-8"))
                        client_sock.close()
                    except Exception:
                        pass
                    continue
                threading.Thread(
                    target=self._guarded_handle_client,
                    args=(client_sock,),
                    daemon=True
                ).start()
            except OSError:
                break

    def _guarded_handle_client(self, client_sock: socket.socket) -> None:
        try:
            self._handle_client(client_sock)
        finally:
            self._concurrency_semaphore.release()

    def _handle_client(self, client_sock: socket.socket) -> None:
        client_sock.settimeout(5.0)
        with client_sock:
            try:
                data = _recv_msg(client_sock)
                if data is None:
                    return
                if len(data) == 0:
                    _send_msg(client_sock, json.dumps({"status": "error", "message": "Empty payload"}).encode("utf-8"))
                    return
                message = json.loads(data.decode("utf-8"))

                # Thread safety: Dispatch UI commands to the GTK main loop if it is active
                if GLib.main_depth() > 0:
                    done_event = threading.Event()
                    result_container = {}

                    def _run_handler():
                        try:
                            result_container["res"] = self.command_handler(message)
                        except Exception as err:
                            result_container["err"] = err
                        finally:
                            done_event.set()
                        return False

                    GLib.idle_add(_run_handler)
                    if done_event.wait(timeout=5.0):
                        if "err" in result_container:
                            raise result_container["err"]
                        response = result_container.get("res", {"status": "ok"})
                    else:
                        response = {"status": "error", "message": "Command execution timed out"}
                else:
                    response = self.command_handler(message)

                _send_msg(client_sock, json.dumps(response).encode("utf-8"))
            except Exception as e:
                try:
                    _send_msg(client_sock, json.dumps({"status": "error", "message": str(e)}).encode("utf-8"))
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
        self._release_lock()


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
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
                s.settimeout(0.5)
                s.connect(self.socket_path)
                return True
        except Exception:
            return False

    def send_command(self, payload: Dict[str, Any], timeout: float = 2.0) -> Optional[Dict[str, Any]]:
        end_time = time.time() + timeout
        while time.time() < end_time:
            try:
                with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
                    s.settimeout(timeout)
                    s.connect(self.socket_path)
                    _send_msg(s, json.dumps(payload).encode("utf-8"))
                    raw = _recv_msg(s)
                    if raw:
                        return json.loads(raw.decode("utf-8"))
                    return None
            except (socket.error, OSError) as e:
                if time.time() + 0.05 < end_time:
                    time.sleep(0.02)
                    continue
                print(f"[IPCClient] Command send failed: {e}")
                return None
            except Exception as e:
                print(f"[IPCClient] Command send failed: {e}")
                return None
        return None
