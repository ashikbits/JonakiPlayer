# SPDX-License-Identifier: GPL-3.0-or-later
"""
Local HTTP Loopback Streaming Bridge for Jonaki Player.
Translates HTTP byte-range requests from MPV into piece requests
served from the local BitTorrent engine.
"""

import os
import sys
import re
import uuid
import socket
import logging
import mimetypes
import threading
from typing import Optional, Tuple
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import unquote, urlparse

from .engine import TorrentEngine

logger = logging.getLogger("Jonaki.TorrentHttpBridge")

RANGE_HEADER_RE = re.compile(r"^bytes=(\d*)-(\d*)$")


def parse_byte_range(range_header: Optional[str], total_size: int) -> Optional[Tuple[int, int]]:
    """
    Parses an HTTP 'Range' header value according to RFC 7233.
    Returns (start_byte, end_byte) inclusive, or None if unsatisfiable.
    """
    if total_size <= 0:
        return None

    if not range_header or not range_header.strip():
        return (0, total_size - 1)

    clean_header = range_header.strip()
    match = RANGE_HEADER_RE.match(clean_header)
    if not match:
        return None

    start_str, end_str = match.groups()

    if not start_str and end_str:
        # Suffix range: bytes=-500 -> last 500 bytes
        length = int(end_str)
        if length <= 0:
            return None
        start = max(0, total_size - length)
        end = total_size - 1
    elif start_str and not end_str:
        # From start to EOF: bytes=500-
        start = int(start_str)
        if start >= total_size:
            return None
        end = total_size - 1
    elif start_str and end_str:
        # Explicit range: bytes=100-200
        start = int(start_str)
        end = int(end_str)
        if start > end or start >= total_size:
            return None
        end = min(end, total_size - 1)
    else:
        return None

    return (start, end)


class BridgeRequestHandler(BaseHTTPRequestHandler):
    """
    Handles loopback HTTP requests from MPV, validating session security,
    byte ranges, and streaming piece data on demand.
    """

    server: "TorrentHttpBridgeServer"

    def log_message(self, format, *args):
        # Prevent cluttering stdout; redirect to module logger
        logger.debug("[Bridge HTTP] %s - %s", self.address_string(), format % args)

    def do_HEAD(self):
        self._handle_request(send_body=False)

    def do_GET(self):
        self._handle_request(send_body=True)

    def _handle_request(self, send_body: bool = True) -> None:
        # 1. Enforce loopback client origin
        client_ip = self.client_address[0]
        if client_ip not in ("127.0.0.1", "::1", "localhost"):
            logger.warning("Rejected non-loopback request from %s", client_ip)
            self.send_error(403, "Forbidden: Loopback access only")
            return

        parsed = urlparse(self.path)
        path = unquote(parsed.path)

        # 2. Validate route and session token: strictly /stream/<session_id>/<filename>
        parts = [p for p in path.split("/") if p]
        if len(parts) != 3 or parts[0] != "stream" or ".." in parts or "." in parts:
            self.send_error(404, "Not Found")
            return

        req_session_id = parts[1]
        bridge = self.server.bridge
        if req_session_id != bridge.session_id:
            logger.warning("Invalid session id: %s (expected %s)", req_session_id, bridge.session_id)
            self.send_error(404, "Session Not Found or Expired")
            return

        req_filename = parts[2]
        engine = bridge.engine
        total_size = engine.get_selected_file_size()
        file_path = engine.get_selected_file_path()

        if total_size <= 0 or not file_path:
            self.send_error(404, "Target file not available")
            return

        expected_filename = os.path.basename(file_path)
        if req_filename != expected_filename:
            logger.warning("Filename mismatch: %s (expected %s)", req_filename, expected_filename)
            self.send_error(404, "File Not Found")
            return

        # 3. Parse Byte-Range header
        range_header = self.headers.get("Range")
        byte_range = parse_byte_range(range_header, total_size)

        if byte_range is None:
            # 416 Range Not Satisfiable
            self.send_response(416)
            self.send_header("Content-Range", f"bytes */{total_size}")
            self.send_header("Accept-Ranges", "bytes")
            self.end_headers()
            return

        start_byte, end_byte = byte_range
        content_len = end_byte - start_byte + 1
        status_code = 206 if range_header else 200

        content_type, _ = mimetypes.guess_type(file_path)
        if not content_type:
            content_type = "video/mp4"

        # 4. Send Response Headers
        self.send_response(status_code)
        self.send_header("Content-Type", content_type)
        self.send_header("Accept-Ranges", "bytes")
        if status_code == 206:
            self.send_header("Content-Range", f"bytes {start_byte}-{end_byte}/{total_size}")
        self.send_header("Content-Length", str(content_len))
        self.send_header("Connection", "keep-alive")
        self.end_headers()

        if not send_body:
            return

        # 5. Stream Body Data
        self._stream_file_range(file_path, start_byte, end_byte)

    def _stream_file_range(self, file_path: str, start_byte: int, end_byte: int) -> None:
        bridge = self.server.bridge
        engine = bridge.engine
        ti = engine.torrent_info
        file_idx = engine.selected_file_index

        if not ti or file_idx is None:
            return

        current_offset = start_byte
        chunk_size = 64 * 1024  # 64 KB write chunks

        # Wait for initial piece to ensure file exists on disk
        initial_piece = ti.map_file(file_idx, current_offset, 1).piece
        if not engine.wait_for_piece(initial_piece, timeout=45.0, cancel_event=bridge.cancel_event):
            logger.warning("Timed out waiting for initial piece %d", initial_piece)
            return

        if not os.path.exists(file_path):
            logger.error("Expected file on disk does not exist: %s", file_path)
            return

        try:
            with open(file_path, "rb") as f:
                while current_offset <= end_byte:
                    if bridge.cancel_event.is_set() or getattr(engine, "handle", None) is None:
                        break

                    req = ti.map_file(file_idx, current_offset, 1)
                    target_piece = req.piece

                    # Wait for piece availability
                    if not engine.have_piece(target_piece):
                        ok = engine.wait_for_piece(
                            target_piece, timeout=45.0, cancel_event=bridge.cancel_event
                        )
                        if not ok or bridge.cancel_event.is_set() or getattr(engine, "handle", None) is None:
                            logger.warning("Aborting read; piece %d unavailable", target_piece)
                            break

                    piece_offset = req.start
                    piece_size = ti.piece_size(target_piece)
                    bytes_remaining_in_piece = piece_size - piece_offset
                    bytes_remaining_in_range = end_byte - current_offset + 1

                    to_read = min(bytes_remaining_in_piece, bytes_remaining_in_range, chunk_size)
                    if to_read <= 0:
                        break

                    f.seek(current_offset)
                    data = f.read(to_read)
                    if not data:
                        break

                    self.wfile.write(data)
                    self.wfile.flush()
                    current_offset += len(data)

        except (BrokenPipeError, ConnectionResetError):
            # Normal behavior when MPV seeks or user changes position
            logger.debug("Client seek/disconnect at byte %d", current_offset)
        except Exception as e:
            logger.error("Streaming error at byte %d: %s", current_offset, e)


class TorrentHttpBridgeServer(ThreadingHTTPServer):
    """Threading HTTPServer instance bound to loopback."""
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, server_address, RequestHandlerClass, bridge: "TorrentHttpBridge"):
        super().__init__(server_address, RequestHandlerClass)
        self.bridge = bridge

    def handle_error(self, request, client_address):
        """Suppress benign socket errors caused by seeking or player disconnects."""
        exc_type, exc_val, _ = sys.exc_info()
        if exc_type in (BrokenPipeError, ConnectionResetError):
            logger.debug("Benign client disconnect from %s: %s", client_address, exc_val)
            return
        super().handle_error(request, client_address)


class TorrentHttpBridge:
    """
    Manages the lifecycle of the loopback HTTP streaming bridge server.
    """

    def __init__(self, engine: TorrentEngine, port: int = 0):
        self.engine = engine
        self.port = port
        self.session_id = uuid.uuid4().hex
        self.cancel_event = threading.Event()
        self.server: Optional[TorrentHttpBridgeServer] = None
        self._server_thread: Optional[threading.Thread] = None

    def start(self) -> str:
        """
        Starts the HTTP loopback bridge server.
        Returns the full loopback stream URL for MPV.
        """
        # Strictly bind to 127.0.0.1
        self.cancel_event.clear()
        self.server = TorrentHttpBridgeServer(
            ("127.0.0.1", self.port), BridgeRequestHandler, self
        )
        # Retrieve actual bound port (important when port=0 was requested)
        self.port = self.server.server_address[1]

        self._server_thread = threading.Thread(
            target=self.server.serve_forever, name="Jonaki-HTTP-Bridge", daemon=True
        )
        self._server_thread.start()

        # Generate stream URL
        target_path = self.engine.get_selected_file_path()
        filename = os.path.basename(target_path) if target_path else "stream.mp4"
        stream_url = f"http://127.0.0.1:{self.port}/stream/{self.session_id}/{filename}"
        logger.info("Torrent loopback bridge started on: %s", stream_url)
        return stream_url

    def get_stream_url(self) -> Optional[str]:
        """Returns the active stream URL if running."""
        if not self.server or not self.port:
            return None
        target_path = self.engine.get_selected_file_path()
        filename = os.path.basename(target_path) if target_path else "stream.mp4"
        return f"http://127.0.0.1:{self.port}/stream/{self.session_id}/{filename}"

    def stop(self) -> None:
        """Stops the HTTP bridge server and cleans up threads."""
        self.cancel_event.set()
        if self.server:
            try:
                self.server.shutdown()
                self.server.server_close()
            except Exception as e:
                logger.warning("Error closing HTTP server: %s", e)
            self.server = None

        if self._server_thread and self._server_thread.is_alive():
            self._server_thread.join(timeout=1.0)
            self._server_thread = None
        logger.info("Torrent loopback bridge stopped.")
