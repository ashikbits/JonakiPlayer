# SPDX-License-Identifier: GPL-3.0-or-later
"""
Torrent Engine Subsystem for Jonaki Player.
Wraps libtorrent 2.x to provide asynchronous metadata resolution,
piece prioritization, deadline scheduling, and clean lifecycle management.
"""

import os
import sys
import time
import logging
import threading
from typing import List, Optional, Tuple, Callable

from .models import TorrentFileInfo, TorrentStatusInfo, is_video_file

logger = logging.getLogger("Jonaki.TorrentEngine")

try:
    import libtorrent as lt
    LIBTORRENT_AVAILABLE = True
except ImportError:
    lt = None
    LIBTORRENT_AVAILABLE = False


def validate_magnet_uri(uri: str) -> bool:
    """Validates that a string is a well-formed magnet URI containing a BTIH info hash."""
    if not isinstance(uri, str):
        return False
    uri_clean = uri.strip()
    if not uri_clean.startswith("magnet:?"):
        return False
    # Check for xt=urn:btih: or xt=urn:btmh:
    return "xt=urn:btih:" in uri_clean or "xt=urn:btmh:" in uri_clean


class TorrentEngine:
    """
    Manages a libtorrent session, active torrent handle, alert worker,
    and piece synchronization.
    """

    def __init__(self, download_dir: Optional[str] = None, listen_port: int = 0):
        if not LIBTORRENT_AVAILABLE:
            raise RuntimeError("libtorrent Python bindings are not installed on this system.")

        if download_dir:
            self.download_dir = download_dir
        else:
            xdg_cache = os.environ.get("XDG_CACHE_HOME", os.path.expanduser("~/.cache"))
            self.download_dir = os.path.join(xdg_cache, "jonaki", "torrents")
        os.makedirs(self.download_dir, exist_ok=True)

        self.listen_port = listen_port
        self.session: Optional[lt.session] = None
        self.handle: Optional[lt.torrent_handle] = None
        self.torrent_info: Optional[lt.torrent_info] = None
        self.selected_file_index: Optional[int] = None

        # Synchronization primitives
        self._lock = threading.RLock()
        self._piece_cond = threading.Condition(self._lock)
        self._metadata_event = threading.Event()
        self._stop_event = threading.Event()

        # Alert worker thread
        self._alert_thread: Optional[threading.Thread] = None
        self._running = False

        # Status tracking
        self._last_error: Optional[str] = None
        self._active_deadlines: dict[int, int] = {}

        self._init_session()

    def _init_session(self) -> None:
        """Initializes the libtorrent session with streaming-friendly settings."""
        params = lt.session_params()
        alert_mask = (
            lt.alert.category_t.status_notification
            | lt.alert.category_t.storage_notification
            | lt.alert.category_t.error_notification
        )

        settings = {
            "alert_mask": alert_mask,
            "alert_queue_size": 10000,
            "connections_limit": 250,
            "active_downloads": 8,
            "active_seeds": 4,
            "torrent_connect_boost": 30,
            "request_queue_time": 3,
            "piece_timeout": 15,
            "enable_dht": True,
            "enable_lsd": True,
            "enable_upnp": True,
            "enable_natpmp": True,
            "dht_bootstrap_nodes": "router.bittorrent.com:6881,dht.transmissionbt.com:6881,router.utorrent.com:6881",
        }
        if self.listen_port > 0:
            settings["listen_interfaces"] = f"0.0.0.0:{self.listen_port},[::]:{self.listen_port}"

        params.settings = settings
        self.session = lt.session(params)
        self._running = True

        self._alert_thread = threading.Thread(
            target=self._alert_loop, name="Jonaki-LT-Alerts", daemon=True
        )
        self._alert_thread.start()

    def _alert_loop(self) -> None:
        """Background thread consuming libtorrent alerts."""
        while self._running and not self._stop_event.is_set():
            if not self.session:
                break
            try:
                if self.session.wait_for_alert(100):
                    alerts = self.session.pop_alerts()
                    for alert in alerts:
                        self._process_alert(alert)
            except Exception as e:
                logger.error("Exception in alert loop: %s", e)
                break

    def _process_alert(self, alert) -> None:
        """Dispatches individual libtorrent alerts."""
        if isinstance(alert, lt.metadata_received_alert):
            if self.handle and alert.handle == self.handle:
                with self._lock:
                    try:
                        self.torrent_info = self.handle.torrent_file()
                    except Exception as e:
                        logger.error("Failed to retrieve torrent_file from handle: %s", e)
                self._metadata_event.set()

        elif isinstance(alert, lt.metadata_failed_alert):
            if self.handle and alert.handle == self.handle:
                self._last_error = f"Metadata retrieval failed: {alert.message()}"
                self._metadata_event.set()

        elif isinstance(alert, lt.piece_finished_alert):
            if self.handle and alert.handle == self.handle:
                with self._lock:
                    piece_idx = alert.piece_index
                    if piece_idx in self._active_deadlines:
                        del self._active_deadlines[piece_idx]
                    self._piece_cond.notify_all()

        elif isinstance(alert, lt.torrent_error_alert):
            if self.handle and alert.handle == self.handle:
                self._last_error = f"Torrent error: {alert.message()} ({alert.error})"
                logger.warning("Torrent error alert: %s", alert.message())

        elif isinstance(alert, lt.tracker_error_alert):
            # Non-fatal tracker warning
            pass

    def add_torrent(self, source: str) -> None:
        """
        Adds a magnet URI or local .torrent file path to the session.
        Cleans up any previously active torrent in this engine instance.
        """
        with self._lock:
            self._cleanup_active_torrent()
            self._metadata_event.clear()
            self._last_error = None
            source_clean = source.strip()

            atp = lt.add_torrent_params()
            atp.save_path = self.download_dir
            atp.storage_mode = lt.storage_mode_t.storage_mode_sparse

            if source_clean.startswith("magnet:"):
                if not validate_magnet_uri(source_clean):
                    raise ValueError("Invalid magnet URI format.")
                magnet_atp = lt.parse_magnet_uri(source_clean)
                magnet_atp.save_path = self.download_dir
                magnet_atp.storage_mode = lt.storage_mode_t.storage_mode_sparse
                magnet_atp.flags |= lt.torrent_flags.sequential_download
                atp = magnet_atp
            else:
                if not os.path.isfile(source_clean):
                    raise FileNotFoundError(f"Torrent file not found: {source_clean}")
                ti = lt.torrent_info(source_clean)
                atp.ti = ti
                atp.flags |= lt.torrent_flags.sequential_download
                self.torrent_info = ti
                self._metadata_event.set()

            self.handle = self.session.add_torrent(atp)
            try:
                self.handle.set_flags(lt.torrent_flags.sequential_download)
            except Exception:
                pass

            # If added from .torrent file, metadata is already available
            if self.handle.status().has_metadata:
                self.torrent_info = self.handle.torrent_file()
                self._metadata_event.set()

    def wait_for_metadata(
        self, timeout: float = 60.0, cancel_event: Optional[threading.Event] = None
    ) -> bool:
        """
        Waits asynchronously for torrent metadata to become available.
        Returns True if metadata is ready, False if timed out or cancelled.
        """
        if not self.handle:
            return False

        with self._lock:
            if self.handle.status().has_metadata and self.torrent_info is not None:
                return True

        start_time = time.time()
        while time.time() - start_time < timeout:
            if cancel_event and cancel_event.is_set():
                return False
            if self._stop_event.is_set():
                return False
            if self._last_error and "Metadata retrieval failed" in self._last_error:
                return False

            if self._metadata_event.wait(0.2):
                with self._lock:
                    if self.handle and self.handle.status().has_metadata:
                        if not self.torrent_info:
                            try:
                                self.torrent_info = self.handle.torrent_file()
                            except Exception:
                                pass
                        if self.torrent_info:
                            return True

            with self._lock:
                if self.handle and self.handle.status().has_metadata:
                    if not self.torrent_info:
                        try:
                            self.torrent_info = self.handle.torrent_file()
                        except Exception:
                            pass
                    if self.torrent_info:
                        return True

        return False

    def get_files(self) -> List[TorrentFileInfo]:
        """Returns the list of files contained in the torrent metadata."""
        with self._lock:
            if not self.torrent_info:
                return []
            ti = self.torrent_info
            files = ti.files()
            result: List[TorrentFileInfo] = []
            for idx in range(ti.num_files()):
                p = files.file_path(idx)
                name = files.file_name(idx)
                size = files.file_size(idx)
                offset = files.file_offset(idx)
                result.append(
                    TorrentFileInfo(
                        index=idx,
                        name=name,
                        path=p,
                        size=size,
                        offset=offset,
                        is_video=is_video_file(name),
                        priority=4,
                    )
                )
            return result

    def get_largest_video_file_index(self) -> Optional[int]:
        """Finds the index of the largest video file in the torrent."""
        files = self.get_files()
        largest_idx = None
        largest_size = -1

        for f in files:
            if f.is_video and f.size > largest_size:
                largest_size = f.size
                largest_idx = f.index

        if largest_idx is None and files:
            # Fallback to largest file overall if no video extension recognized
            for f in files:
                if f.size > largest_size:
                    largest_size = f.size
                    largest_idx = f.index

        return largest_idx

    def select_file_for_playback(self, file_index: int) -> None:
        """
        Prioritizes the selected file for streaming (priority 4 / default)
        and disables download for all other files in multi-file torrents (priority 0).
        """
        with self._lock:
            if not self.handle or not self.torrent_info:
                raise RuntimeError("Torrent metadata not ready.")

            num_files = self.torrent_info.num_files()
            if file_index < 0 or file_index >= num_files:
                raise IndexError(f"File index {file_index} out of range (0..{num_files - 1}).")

            self.selected_file_index = file_index
            priorities = [0] * num_files
            priorities[file_index] = 4
            self.handle.prioritize_files(priorities)
            try:
                self.handle.set_flags(lt.torrent_flags.sequential_download)
            except Exception:
                pass

    def get_selected_file_path(self) -> Optional[str]:
        """Returns the absolute filesystem path of the currently selected file."""
        with self._lock:
            if (
                not self.handle
                or not self.torrent_info
                or self.selected_file_index is None
            ):
                return None
            save_path = self.handle.status().save_path
            rel_path = self.torrent_info.files().file_path(self.selected_file_index)
            return os.path.join(save_path, rel_path)

    def get_selected_file_size(self) -> int:
        """Returns the size in bytes of the selected file."""
        with self._lock:
            if (
                not self.torrent_info
                or self.selected_file_index is None
            ):
                return 0
            return self.torrent_info.files().file_size(self.selected_file_index)

    def get_piece_range_for_file(self, file_index: int) -> Tuple[int, int]:
        """Returns (first_piece_index, last_piece_index) for the given file."""
        with self._lock:
            if not self.torrent_info:
                return (0, 0)
            ti = self.torrent_info
            size = ti.files().file_size(file_index)
            if size == 0:
                return (0, 0)
            req_start = ti.map_file(file_index, 0, 1)
            req_end = ti.map_file(file_index, max(0, size - 1), 1)
            return (req_start.piece, req_end.piece)

    def prioritize_critical_pieces(self, file_index: int) -> None:
        """
        Pre-prioritizes the head (first 8 pieces) and tail (last 8 pieces) of the file
        with top priority (7) and deadline 0 to ensure fast container probing by MPV.
        """
        with self._lock:
            if not self.handle or not self.torrent_info:
                return
            first_p, last_p = self.get_piece_range_for_file(file_index)
            if first_p > last_p:
                return

            critical: set[int] = set()
            for p in range(first_p, min(first_p + 8, last_p + 1)):
                critical.add(p)
            for p in range(max(first_p, last_p - 7), last_p + 1):
                critical.add(p)

            for p in critical:
                if not self.have_piece(p):
                    try:
                        self.handle.piece_priority(p, 7)
                        self.handle.set_piece_deadline(p, 0, lt.deadline_flags_t.alert_when_available)
                    except Exception:
                        try:
                            self.handle.set_piece_deadline(p, 0)
                        except Exception:
                            pass

    def have_piece(self, piece_index: int) -> bool:
        """Checks if a piece has been downloaded and verified on disk."""
        with self._lock:
            if not self.handle:
                return False
            try:
                return bool(self.handle.have_piece(piece_index))
            except Exception:
                return False

    def set_piece_deadline(self, piece_index: int, deadline_ms: int = 0) -> None:
        """Sets a download deadline for a piece in milliseconds (0 = urgent)."""
        with self._lock:
            if not self.handle:
                return
            if not self.have_piece(piece_index):
                self._active_deadlines[piece_index] = self._active_deadlines.get(piece_index, 0) + 1
                try:
                    self.handle.set_piece_deadline(piece_index, deadline_ms, lt.deadline_flags_t.alert_when_available)
                except Exception:
                    try:
                        self.handle.set_piece_deadline(piece_index, deadline_ms)
                    except Exception:
                        pass

    def reset_piece_deadline(self, piece_index: int) -> None:
        """Resets the deadline on a piece if no longer urgently required."""
        with self._lock:
            if not self.handle:
                return
            if piece_index in self._active_deadlines:
                self._active_deadlines[piece_index] -= 1
                if self._active_deadlines[piece_index] <= 0:
                    del self._active_deadlines[piece_index]
                    if not self.have_piece(piece_index):
                        try:
                            self.handle.reset_piece_deadline(piece_index)
                        except Exception:
                            pass

    def clear_piece_deadlines(self) -> None:
        """Clears all active piece deadlines."""
        with self._lock:
            if not self.handle:
                return
            self._active_deadlines.clear()
            try:
                self.handle.clear_piece_deadlines()
            except Exception:
                pass

    def wait_for_piece(
        self,
        piece_index: int,
        timeout: float = 30.0,
        cancel_event: Optional[threading.Event] = None,
    ) -> bool:
        """
        Synchronously waits until a piece is downloaded and verified.
        Sets urgent deadline on the piece and sliding lookahead deadlines on subsequent pieces.
        """
        with self._piece_cond:
            if not self.handle:
                return False
            if self.have_piece(piece_index):
                return True

            # Urgent request for the current piece
            self.set_piece_deadline(piece_index, 0)

            # Lookahead window of 8 subsequent pieces with progressive deadlines
            if self.selected_file_index is not None and self.torrent_info:
                _, last_p = self.get_piece_range_for_file(self.selected_file_index)
                for step in range(1, 9):
                    next_p = piece_index + step
                    if next_p <= last_p and not self.have_piece(next_p):
                        self.set_piece_deadline(next_p, step * 1000)

            start_t = time.time()
            while not self.have_piece(piece_index):
                if cancel_event and cancel_event.is_set():
                    return False
                if self._stop_event.is_set() or not self.handle:
                    return False
                remaining = timeout - (time.time() - start_t)
                if remaining <= 0:
                    return False
                # Wait on condition variable or wake every 250ms
                wait_step = min(remaining, 0.25)
                self._piece_cond.wait(wait_step)

            return True

    def get_status(self) -> TorrentStatusInfo:
        """Retrieves live metrics of the torrent session."""
        with self._lock:
            info = TorrentStatusInfo()
            if not self.handle:
                return info

            try:
                st = self.handle.status()
                info.has_metadata = bool(st.has_metadata)
                info.name = st.name or (self.torrent_info.name() if self.torrent_info else "")
                info.progress = float(st.progress)
                info.download_rate = int(st.download_rate)
                info.upload_rate = int(st.upload_rate)
                info.num_peers = int(st.num_peers)
                info.num_seeds = int(st.num_seeds)
                info.state = str(st.state)
                info.total_size = int(st.total_wanted) if st.total_wanted > 0 else (
                    self.torrent_info.total_size() if self.torrent_info else 0
                )
                info.selected_file_index = self.selected_file_index
                info.error_message = self._last_error

                if self.torrent_info:
                    info.piece_count = self.torrent_info.num_pieces()
                    info.pieces_completed = int(st.num_pieces)
                    info.files = self.get_files()
            except Exception as e:
                info.error_message = str(e)

            return info

    def _cleanup_active_torrent(self) -> None:
        """Internal helper to remove the active torrent without stopping the engine."""
        if self.handle and self.session:
            try:
                self.clear_piece_deadlines()
                # Remove from session without deleting files
                self.session.remove_torrent(self.handle, 0)
            except Exception as e:
                logger.warning("Error removing torrent from session: %s", e)
            self.handle = None
            self.torrent_info = None
            self.selected_file_index = None

    def stop(self) -> None:
        """Stops the torrent session, alert loop, and releases all resources."""
        self._stop_event.set()
        self._running = False
        with self._lock:
            self._cleanup_active_torrent()
            self._piece_cond.notify_all()
            self._metadata_event.set()

        if self._alert_thread and self._alert_thread.is_alive():
            self._alert_thread.join(timeout=1.0)
            self._alert_thread = None

        if self.session:
            try:
                del self.session
            except Exception:
                pass
            self.session = None
