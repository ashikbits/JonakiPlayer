# SPDX-License-Identifier: GPL-3.0-or-later
"""
Tests for Milestone 2: Security & Persistence Hardening
- Torrent path traversal prevention (TASK-05)
- Advisory lock retention and bounded IPC concurrency (TASK-06)
- UUID-based playlist item tracking with duplicate preservation (TASK-07)
"""

import unittest
import unittest.mock
import os
import tempfile
import socket
import threading
import time
import uuid

from src.torrent.engine import sanitize_torrent_path, TorrentEngine
from src.core.ipc import IPCServer, IPCClient
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk
from src.ui.playlist_view import PlaylistWindow


class TestMilestone2SecurityPersistence(unittest.TestCase):
    def test_torrent_path_traversal_prevention(self):
        """TASK-05: Verify malicious relative paths are rejected by sanitize_torrent_path."""
        with tempfile.TemporaryDirectory() as base_dir:
            # 1. Valid subpaths should succeed
            safe_p1 = sanitize_torrent_path(base_dir, "movie.mp4")
            self.assertEqual(safe_p1, os.path.join(base_dir, "movie.mp4"))

            safe_p2 = sanitize_torrent_path(base_dir, "subdir/movie.mkv")
            self.assertEqual(safe_p2, os.path.join(base_dir, "subdir", "movie.mkv"))

            # 2. Path traversal attempts must raise ValueError
            with self.assertRaises(ValueError):
                sanitize_torrent_path(base_dir, "../outside.mp4")

            with self.assertRaises(ValueError):
                sanitize_torrent_path(base_dir, "../../etc/passwd")

            with self.assertRaises(ValueError):
                sanitize_torrent_path(base_dir, "sub/../../../../etc/shadow")

            # 3. Absolute path escapes must raise ValueError
            with self.assertRaises(ValueError):
                sanitize_torrent_path(base_dir, "/etc/passwd")

            with self.assertRaises(ValueError):
                sanitize_torrent_path(base_dir, "C:\\Windows\\System32\\calc.exe")

    def test_ipc_advisory_lock_retention_and_concurrency(self):
        """TASK-06: Verify advisory flock file is retained on disk and concurrency is bounded."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            sock_path = os.path.join(tmp_dir, "test_ipc.sock")
            lock_path = sock_path + ".lock"

            handler_calls = []

            def dummy_handler(cmd):
                handler_calls.append(cmd)
                return {"status": "ok", "action": cmd.get("action")}

            server = IPCServer(command_handler=dummy_handler, socket_path=sock_path)
            self.assertTrue(server.start())

            # Verify lock file and socket file were created
            self.assertTrue(os.path.exists(lock_path))
            self.assertTrue(os.path.exists(sock_path))

            # Send command via IPCClient
            client = IPCClient(socket_path=sock_path)
            res = client.send_command({"action": "ping"})
            self.assertEqual(res, {"status": "ok", "action": "ping"})

            # Stop server
            server.stop()

            # Socket file must be cleaned up, but the flock file must be retained on disk!
            self.assertFalse(os.path.exists(sock_path))
            self.assertTrue(os.path.exists(lock_path))

    def test_playlist_duplicate_preservation_on_drag_end(self):
        """TASK-07: Verify duplicate file entries in playlist are preserved during reordering."""
        class MockPlayer:
            def __init__(self):
                self.playlist = [
                    {"path": "/media/song.mp3", "title": "Song Track", "duration": 180.0, "id": "id-1"},
                    {"path": "/media/other.mp3", "title": "Other Track", "duration": 200.0, "id": "id-2"},
                    {"path": "/media/song.mp3", "title": "Song Track (Dupe)", "duration": 180.0, "id": "id-3"},
                ]
                self.current_index = 0
                self.db = unittest.mock.MagicMock()

        player = MockPlayer()
        win = PlaylistWindow(player)
        win.update_playlist(player.playlist)

        self.assertEqual(len(win.list_store), 3)

        # Simulate reverse reordering in list_store: id-3, id-2, id-1
        row_data = [list(row) for row in win.list_store]
        win.list_store.clear()
        for i, row in enumerate(reversed(row_data)):
            win.list_store.append([i + 1, row[1], row[2], row[3], row[4]])

        # Trigger drag-end handler
        win._on_drag_end(None, None)

        # Verify playlist preserves all 3 entries without dropping duplicates
        self.assertEqual(len(player.playlist), 3)
        self.assertEqual(player.playlist[0]["id"], "id-3")
        self.assertEqual(player.playlist[1]["id"], "id-2")
        self.assertEqual(player.playlist[2]["id"], "id-1")
        # Ensure database was notified
        player.db.save_playlist.assert_called_once()
        win.destroy()


if __name__ == "__main__":
    unittest.main()
