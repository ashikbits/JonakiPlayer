# SPDX-License-Identifier: GPL-3.0-or-later
"""
Torrent Stream Manager for Jonaki Player.
Coordinates between TorrentEngine, TorrentHttpBridge, and the player UI/engine.
Ensures deterministic lifecycle transitions and leak-free session cleanup.
"""

import logging
import threading
from typing import Optional, Callable

from .models import TorrentStatusInfo, TorrentFileInfo
from .engine import TorrentEngine, validate_magnet_uri
from .http_bridge import TorrentHttpBridge

logger = logging.getLogger("Jonaki.TorrentManager")


class TorrentStreamManager:
    """
    High-level manager orchestrating torrent loading, metadata acquisition,
    file selection, loopback HTTP streaming, and teardown.
    """

    def __init__(self, download_dir: Optional[str] = None):
        self.download_dir = download_dir
        self.engine: Optional[TorrentEngine] = None
        self.bridge: Optional[TorrentHttpBridge] = None
        self._lock = threading.RLock()
        self._active_source: Optional[str] = None
        self._stream_url: Optional[str] = None

    @property
    def is_streaming(self) -> bool:
        """Returns True if a torrent is currently being streamed via the HTTP bridge."""
        with self._lock:
            return bool(self.bridge and self.bridge.server is not None)

    @property
    def active_source(self) -> Optional[str]:
        return self._active_source

    @property
    def stream_url(self) -> Optional[str]:
        return self._stream_url

    def prepare_torrent(
        self,
        source: str,
        timeout: float = 60.0,
        cancel_event: Optional[threading.Event] = None,
        on_metadata_ready: Optional[Callable[[TorrentStatusInfo], None]] = None,
    ) -> TorrentStatusInfo:
        """
        Loads the torrent source and waits for metadata to become available.
        Does not yet start the HTTP streaming bridge until a file is selected.
        """
        with self._lock:
            self.stop_session()
            self._active_source = source

            self.engine = TorrentEngine(download_dir=self.download_dir)
            self.engine.add_torrent(source)
            engine = self.engine

        # Wait for metadata outside the main lock so cancel/status calls are responsive
        ready = engine.wait_for_metadata(timeout=timeout, cancel_event=cancel_event)
        if not ready:
            if cancel_event and cancel_event.is_set():
                raise InterruptedError("Metadata retrieval was cancelled by user.")
            last_err = engine.get_status().error_message
            raise TimeoutError(last_err or "Timed out retrieving torrent metadata.")

        status = engine.get_status()
        if on_metadata_ready:
            on_metadata_ready(status)

        return status

    def start_streaming(self, file_index: Optional[int] = None) -> str:
        """
        Selects a file for playback, pre-prioritizes critical pieces,
        starts the loopback HTTP bridge, and returns the stream URL.
        """
        with self._lock:
            if not self.engine or not self.engine.torrent_info:
                raise RuntimeError("Torrent engine not initialized or metadata missing.")

            # Select file
            if file_index is None:
                file_index = self.engine.get_largest_video_file_index()
                if file_index is None:
                    file_index = 0

            self.engine.select_file_for_playback(file_index)
            self.engine.prioritize_critical_pieces(file_index)

            # Clean previous bridge if any
            if self.bridge:
                self.bridge.stop()
                self.bridge = None

            # Start HTTP Loopback Bridge
            self.bridge = TorrentHttpBridge(engine=self.engine)
            self._stream_url = self.bridge.start()
            return self._stream_url

    def get_status(self) -> TorrentStatusInfo:
        """Returns the current status of the torrent session."""
        with self._lock:
            if not self.engine:
                return TorrentStatusInfo(state="idle")
            return self.engine.get_status()

    def stop_session(self) -> None:
        """
        Stops the HTTP bridge, cancels downloads, and releases all resources.
        Guarantees no orphaned threads, sockets, or locks.
        """
        with self._lock:
            if self.bridge:
                try:
                    self.bridge.stop()
                except Exception as e:
                    logger.warning("Error stopping bridge: %s", e)
                self.bridge = None

            if self.engine:
                try:
                    self.engine.stop()
                except Exception as e:
                    logger.warning("Error stopping engine: %s", e)
                self.engine = None

            self._active_source = None
            self._stream_url = None
