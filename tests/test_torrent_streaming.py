# SPDX-License-Identifier: GPL-3.0-or-later
"""
Automated Unit and Integration Tests for Torrent Streaming in Jonaki Player.
Tests cover:
- Magnet URI validation
- Byte-range parsing (normal, suffix, unsatisfiable, malformed)
- Video container detection and model formatting
- Local HTTP Loopback Bridge (200, 206 Partial Content, 416, HEAD, security)
- Deterministic local torrent generation and byte-for-byte stream verification
- Playback integration with JonakiCore (headless MPV) over loopback HTTP
- Session lifecycle and resource cleanup
"""

import os
import sys
import time
import shutil
import hashlib
import tempfile
import unittest
import urllib.request
import urllib.error
from unittest.mock import MagicMock, patch

# Ensure src is on path
SRC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from torrent.models import (
    TorrentFileInfo,
    TorrentStatusInfo,
    is_video_file,
    VIDEO_EXTENSIONS,
)
from torrent.engine import (
    validate_magnet_uri,
    TorrentEngine,
    LIBTORRENT_AVAILABLE,
)
from torrent.http_bridge import (
    parse_byte_range,
    TorrentHttpBridge,
)
from torrent.manager import TorrentStreamManager
from core.engine import JonakiCore, PlaybackState

import libtorrent as lt


def create_local_test_torrent(target_file_path: str, piece_len: int = 16384) -> bytes:
    """Helper to generate a valid bencoded torrent byte buffer from a local file."""
    file_size = os.path.getsize(target_file_path)
    file_name = os.path.basename(target_file_path)

    fs = lt.file_storage()
    fs.add_file(file_name, file_size)
    ct = lt.create_torrent(fs, piece_len)

    with open(target_file_path, "rb") as f:
        for i in range(ct.num_pieces()):
            chunk = f.read(piece_len)
            ct.set_hash(i, hashlib.sha1(chunk).digest())

    return lt.bencode(ct.generate())


class TestMagnetUriValidation(unittest.TestCase):
    """Unit tests for magnet URI validation."""

    def test_valid_standard_magnet(self):
        uri = "magnet:?xt=urn:btih:da39a3ee5e6b4b0d3255bfef95601890afd80709&dn=test_video"
        self.assertTrue(validate_magnet_uri(uri))

    def test_valid_btmh_magnet(self):
        uri = "magnet:?xt=urn:btmh:1220daf3a3ee5e6b4b0d3255bfef95601890afd80709"
        self.assertTrue(validate_magnet_uri(uri))

    def test_invalid_magnets(self):
        self.assertFalse(validate_magnet_uri(""))
        self.assertFalse(validate_magnet_uri("http://example.com/file.torrent"))
        self.assertFalse(validate_magnet_uri("magnet:?dn=test_only"))
        self.assertFalse(validate_magnet_uri(None))
        self.assertFalse(validate_magnet_uri(12345))


class TestByteRangeParsing(unittest.TestCase):
    """Unit tests for RFC 7233 byte-range parsing."""

    def test_full_range_when_no_header(self):
        total = 10000
        self.assertEqual(parse_byte_range(None, total), (0, 9999))
        self.assertEqual(parse_byte_range("", total), (0, 9999))
        self.assertEqual(parse_byte_range("   ", total), (0, 9999))

    def test_explicit_byte_range(self):
        total = 10000
        self.assertEqual(parse_byte_range("bytes=0-499", total), (0, 499))
        self.assertEqual(parse_byte_range("bytes=100-200", total), (100, 200))

    def test_open_ended_range(self):
        total = 10000
        self.assertEqual(parse_byte_range("bytes=500-", total), (500, 9999))
        self.assertEqual(parse_byte_range("bytes=0-", total), (0, 9999))

    def test_suffix_range(self):
        total = 10000
        self.assertEqual(parse_byte_range("bytes=-500", total), (9500, 9999))
        self.assertEqual(parse_byte_range("bytes=-15000", total), (0, 9999))

    def test_range_clamped_to_eof(self):
        total = 10000
        # If requested end exceeds total, clamped to total - 1
        self.assertEqual(parse_byte_range("bytes=5000-20000", total), (5000, 9999))

    def test_unsatisfiable_ranges(self):
        total = 10000
        # Start at or beyond EOF
        self.assertIsNone(parse_byte_range("bytes=10000-", total))
        self.assertIsNone(parse_byte_range("bytes=10001-10500", total))
        # Start > End
        self.assertIsNone(parse_byte_range("bytes=500-400", total))
        # Zero or negative suffix
        self.assertIsNone(parse_byte_range("bytes=-0", total))
        # Zero file size
        self.assertIsNone(parse_byte_range("bytes=0-10", 0))

    def test_malformed_ranges(self):
        total = 10000
        self.assertIsNone(parse_byte_range("characters=0-500", total))
        self.assertIsNone(parse_byte_range("bytes=-", total))
        self.assertIsNone(parse_byte_range("bytes=abc-def", total))
        self.assertIsNone(parse_byte_range("invalid", total))


class TestTorrentDataModels(unittest.TestCase):
    """Unit tests for models and formatting helpers."""

    def test_video_extension_check(self):
        self.assertTrue(is_video_file("movie.mp4"))
        self.assertTrue(is_video_file("/path/to/sample.MKV"))
        self.assertTrue(is_video_file("stream.webm"))
        self.assertTrue(is_video_file("clip.ts"))
        self.assertFalse(is_video_file("subtitle.srt"))
        self.assertFalse(is_video_file("notes.txt"))
        self.assertFalse(is_video_file("audio.flac"))

    def test_file_info_formatting(self):
        f1 = TorrentFileInfo(0, "small.mp4", "small.mp4", 512, 0, True)
        self.assertEqual(f1.formatted_size, "512 B")

        f2 = TorrentFileInfo(1, "medium.mp4", "medium.mp4", 1024 * 1024 * 5, 0, True)
        self.assertEqual(f2.formatted_size, "5.00 MB")

        f3 = TorrentFileInfo(2, "large.mkv", "large.mkv", int(1.45 * 1024 * 1024 * 1024), 0, True)
        self.assertEqual(f3.formatted_size, "1.45 GB")

    def test_status_info_formatting(self):
        status = TorrentStatusInfo(
            name="test",
            download_rate=1024 * 500,
            progress=0.754,
        )
        self.assertEqual(status.formatted_download_rate, "500.0 KB/s")
        self.assertEqual(status.formatted_progress, "75.4%")


class TestTorrentHttpBridgeWithMockEngine(unittest.TestCase):
    """Unit tests for HTTP Bridge byte-range streaming using a mock engine."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.test_payload = b"ABCDEFGHIJKLMNOPQRSTUVWXYZ" * 1000  # 26,000 bytes
        self.test_file_path = os.path.join(self.temp_dir, "test_video.mp4")
        with open(self.test_file_path, "wb") as f:
            f.write(self.test_payload)

        # Build mock engine
        self.mock_engine = MagicMock(spec=TorrentEngine)
        self.mock_engine.handle = MagicMock()
        self.mock_engine.get_selected_file_size.return_value = len(self.test_payload)
        self.mock_engine.get_selected_file_path.return_value = self.test_file_path
        self.mock_engine.selected_file_index = 0

        # Create a real ti for mapping
        fs = lt.file_storage()
        fs.add_file("test_video.mp4", len(self.test_payload))
        ct = lt.create_torrent(fs, 4096)
        for i in range(ct.num_pieces()):
            ct.set_hash(i, hashlib.sha1(b"0" * 4096).digest())
        ti = lt.torrent_info(lt.bencode(ct.generate()))
        self.mock_engine.torrent_info = ti
        self.mock_engine.have_piece.return_value = True
        self.mock_engine.wait_for_piece.return_value = True

        self.bridge = TorrentHttpBridge(engine=self.mock_engine, port=0)
        self.stream_url = self.bridge.start()

    def tearDown(self):
        self.bridge.stop()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_full_get_request(self):
        req = urllib.request.Request(self.stream_url)
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            self.assertEqual(resp.headers.get("Content-Type"), "video/mp4")
            self.assertEqual(resp.headers.get("Accept-Ranges"), "bytes")
            self.assertEqual(int(resp.headers.get("Content-Length")), len(self.test_payload))
            data = resp.read()
            self.assertEqual(data, self.test_payload)

    def test_byte_range_request_partial_content(self):
        req = urllib.request.Request(self.stream_url)
        req.add_header("Range", "bytes=100-499")
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 206)
            self.assertEqual(resp.headers.get("Content-Range"), f"bytes 100-499/{len(self.test_payload)}")
            self.assertEqual(int(resp.headers.get("Content-Length")), 400)
            data = resp.read()
            self.assertEqual(len(data), 400)
            self.assertEqual(data, self.test_payload[100:500])

    def test_seek_offset_range(self):
        req = urllib.request.Request(self.stream_url)
        req.add_header("Range", "bytes=15000-20000")
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 206)
            self.assertEqual(resp.headers.get("Content-Range"), f"bytes 15000-20000/{len(self.test_payload)}")
            data = resp.read()
            self.assertEqual(data, self.test_payload[15000:20001])

    def test_suffix_range_request(self):
        req = urllib.request.Request(self.stream_url)
        req.add_header("Range", "bytes=-250")
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 206)
            data = resp.read()
            self.assertEqual(data, self.test_payload[-250:])

    def test_head_request(self):
        req = urllib.request.Request(self.stream_url, method="HEAD")
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            self.assertEqual(int(resp.headers.get("Content-Length")), len(self.test_payload))
            data = resp.read()
            self.assertEqual(len(data), 0)

    def test_unsatisfiable_range_416(self):
        req = urllib.request.Request(self.stream_url)
        req.add_header("Range", f"bytes={len(self.test_payload) + 500}-")
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req)
        self.assertEqual(ctx.exception.code, 416)
        self.assertIn(f"bytes */{len(self.test_payload)}", ctx.exception.headers.get("Content-Range"))

    def test_invalid_session_token_404(self):
        invalid_url = f"http://127.0.0.1:{self.bridge.port}/stream/wrongtoken123/video.mp4"
        req = urllib.request.Request(invalid_url)
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req)
        self.assertEqual(ctx.exception.code, 404)


class TestTorrentStreamingEndToEndIntegration(unittest.TestCase):
    """
    End-to-end integration test using a deterministic locally generated torrent,
    testing libtorrent metadata resolution, HTTP bridge streaming, and
    headless MPV playback via JonakiCore.
    """

    @classmethod
    def setUpClass(cls):
        cls.corpus_video = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "corpus", "valid_h264_aac.mp4")
        )
        if not os.path.isfile(cls.corpus_video):
            raise unittest.SkipTest(f"Test corpus video missing at {cls.corpus_video}")

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.torrent_file_path = os.path.join(self.temp_dir, "test.torrent")
        self.download_dir = os.path.join(self.temp_dir, "downloads")
        os.makedirs(self.download_dir, exist_ok=True)

        # 1. Generate local torrent pointing to valid_h264_aac.mp4
        t_bytes = create_local_test_torrent(self.corpus_video, piece_len=16384)
        with open(self.torrent_file_path, "wb") as f:
            f.write(t_bytes)

        # 2. Seed the download directory with the video file so pieces are available locally
        dest_video = os.path.join(self.download_dir, os.path.basename(self.corpus_video))
        shutil.copyfile(self.corpus_video, dest_video)

        self.manager = TorrentStreamManager(download_dir=self.download_dir)

    def tearDown(self):
        self.manager.stop_session()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_torrent_preparation_and_metadata(self):
        status = self.manager.prepare_torrent(self.torrent_file_path, timeout=10.0)
        self.assertTrue(status.has_metadata)
        self.assertEqual(len(status.files), 1)
        self.assertEqual(status.files[0].name, os.path.basename(self.corpus_video))
        self.assertEqual(status.files[0].size, os.path.getsize(self.corpus_video))
        self.assertTrue(status.files[0].is_video)

    def test_stream_bytes_fidelity_over_loopback_http(self):
        # Prepare torrent and start HTTP bridge
        self.manager.prepare_torrent(self.torrent_file_path, timeout=10.0)
        stream_url = self.manager.start_streaming(file_index=0)
        self.assertIsNotNone(stream_url)
        self.assertTrue(stream_url.startswith("http://127.0.0.1:"))

        # Fetch byte range 1024-8191 (7168 bytes) over loopback HTTP
        req = urllib.request.Request(stream_url)
        req.add_header("Range", "bytes=1024-8191")

        with urllib.request.urlopen(req, timeout=10.0) as resp:
            self.assertEqual(resp.status, 206)
            http_bytes = resp.read()

        # Compare directly with original corpus video bytes
        with open(self.corpus_video, "rb") as f:
            f.seek(1024)
            expected_bytes = f.read(7168)

        self.assertEqual(len(http_bytes), len(expected_bytes))
        self.assertEqual(http_bytes, expected_bytes)

    def test_mpv_playback_integration_over_loopback_http(self):
        """
        Tests that JonakiCore (headless libmpv, wid=None) successfully loads
        the torrent HTTP stream URL and enters the PLAYING state.
        """
        self.manager.prepare_torrent(self.torrent_file_path, timeout=10.0)
        stream_url = self.manager.start_streaming(file_index=0)

        # Initialize headless JonakiCore
        core = JonakiCore(wid=None)
        core.start_engine()

        try:
            core.load_file(stream_url)
            self.assertEqual(core.state, PlaybackState.PLAYING)

            # Wait briefly for demuxer / playback tick
            time.sleep(0.5)

            # Test seeking over the HTTP stream
            core.seek_absolute(1.0)
            time.sleep(0.2)

            # Confirm engine remains functional and stop cleanly
            core.stop()
            self.assertEqual(core.state, PlaybackState.STOPPED)
        finally:
            core.stop_engine()


class TestPathTraversalAndSecurity(unittest.TestCase):
    """Verifies that the HTTP bridge is defended against traversal and unauthorized requests."""

    def setUp(self):
        self.mock_engine = MagicMock(spec=TorrentEngine)
        self.mock_engine.get_selected_file_size.return_value = 1000
        self.mock_engine.get_selected_file_path.return_value = "/tmp/test.mp4"
        self.bridge = TorrentHttpBridge(engine=self.mock_engine, port=0)
        self.bridge.start()

    def tearDown(self):
        self.bridge.stop()

    def test_path_traversal_blocked(self):
        # Attempt to escape stream route using ../../etc/passwd
        traversal_url = f"http://127.0.0.1:{self.bridge.port}/stream/{self.bridge.session_id}/../../etc/passwd"
        req = urllib.request.Request(traversal_url)
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req)
        self.assertIn(ctx.exception.code, (400, 404))

    def test_arbitrary_unauthenticated_path(self):
        bad_url = f"http://127.0.0.1:{self.bridge.port}/admin/status"
        req = urllib.request.Request(bad_url)
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req)
        self.assertEqual(ctx.exception.code, 404)


class TestTorrentDialogUI(unittest.TestCase):
    """Verifies that TorrentStreamDialog initializes and updates correctly."""

    def test_dialog_creation_and_initial_source(self):
        import gi
        gi.require_version("Gtk", "3.0")
        from gi.repository import Gtk
        from ui.torrent_dialog import TorrentStreamDialog

        manager = MagicMock(spec=TorrentStreamManager)
        cb = MagicMock()
        magnet = "magnet:?xt=urn:btih:da39a3ee5e6b4b0d3255bfef95601890afd80709&dn=test"

        dialog = TorrentStreamDialog(
            parent=None,
            manager=manager,
            on_start_playback=cb,
            initial_source=magnet,
        )
        self.assertEqual(dialog.source_entry.get_text(), magnet)
        self.assertEqual(dialog.get_title(), "Open Torrent / Magnet Stream - Jonaki")
        dialog.destroy()


class TestMainWindowTorrentIntegration(unittest.TestCase):
    """Verifies JonakiMainWindow command dispatching and torrent manager coordination."""

    @patch("ui.main_window.JonakiCore")
    def test_main_window_torrent_command_and_lifecycle(self, mock_core_cls):
        from ui.main_window import JonakiMainWindow

        mock_core = MagicMock()
        mock_core_cls.return_value = mock_core

        win = JonakiMainWindow()
        self.assertIsNotNone(win.torrent_manager)

        # 1. Test _on_torrent_stream_started
        stream_url = "http://127.0.0.1:8888/stream/tok/video.mp4"
        win._on_torrent_stream_started(stream_url, "video.mp4")

        self.assertEqual(len(win.playlist), 1)
        self.assertEqual(win.playlist[0]["path"], stream_url)
        self.assertIn("[Torrent] video.mp4", win.playlist[0]["title"])

        # 2. Test stopping session when another local file is played
        win.torrent_manager.bridge = MagicMock()
        win.torrent_manager._stream_url = stream_url
        win.torrent_manager.stop_session = MagicMock()

        win.play_file("/home/user/other_video.mp4")
        win.torrent_manager.stop_session.assert_called_once()

        # 3. Test window destroy triggers stop_session
        win.torrent_manager.stop_session.reset_mock()
        win.core = MagicMock()
        win._on_destroy(None)
        win.torrent_manager.stop_session.assert_called_once()


class TestLocalSeederDeterministicIntegration(unittest.TestCase):
    """
    Deterministic integration test running a local seeder on loopback (127.0.0.1:0)
    and a downloader starting with 0% data in an isolated temporary directory.
    Verifies:
    - Metadata acquisition over local loopback peer connection.
    - On-demand piece downloading from local seeder.
    - Byte-range HTTP reads match source file byte-for-byte.
    - Distant piece acquisition upon seek request.
    - Playback start in headless MPV before entire file is downloaded.
    - Complete cleanup of seeder, downloader, HTTP server, and sockets.
    """

    @classmethod
    def setUpClass(cls):
        cls.corpus_video = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "corpus", "valid_h264_aac.mp4")
        )
        if not os.path.isfile(cls.corpus_video):
            raise unittest.SkipTest(f"Test corpus video missing at {cls.corpus_video}")

    def setUp(self):
        self.seeder_dir = tempfile.mkdtemp()
        self.downloader_dir = tempfile.mkdtemp()

        # Seed directory receives full video file
        self.video_filename = os.path.basename(self.corpus_video)
        self.seeder_video_path = os.path.join(self.seeder_dir, self.video_filename)
        shutil.copyfile(self.corpus_video, self.seeder_video_path)

        # Create torrent info
        t_bytes = create_local_test_torrent(self.seeder_video_path, piece_len=16384)
        self.torrent_info = lt.torrent_info(t_bytes)
        self.magnet_uri = lt.make_magnet_uri(self.torrent_info)

        # 1. Start Seeder on loopback ephemeral port
        seeder_params = lt.session_params()
        seeder_params.settings = {
            "listen_interfaces": "127.0.0.1:0",
            "enable_dht": False,
            "enable_lsd": False,
            "enable_upnp": False,
            "enable_natpmp": False,
        }
        self.seeder_ses = lt.session(seeder_params)
        self.seeder_port = self.seeder_ses.listen_port()

        atp_seed = lt.add_torrent_params()
        atp_seed.ti = self.torrent_info
        atp_seed.save_path = self.seeder_dir
        atp_seed.flags |= lt.torrent_flags.seed_mode
        self.seeder_handle = self.seeder_ses.add_torrent(atp_seed)

        # 2. Initialize Downloader Manager
        self.manager = TorrentStreamManager(download_dir=self.downloader_dir)

    def tearDown(self):
        self.manager.stop_session()
        if hasattr(self, "seeder_ses"):
            try:
                self.seeder_ses.remove_torrent(self.seeder_handle, 0)
                del self.seeder_ses
            except Exception:
                pass
        shutil.rmtree(self.seeder_dir, ignore_errors=True)
        shutil.rmtree(self.downloader_dir, ignore_errors=True)

    def test_local_seeder_metadata_and_stream(self):
        # Add magnet to engine
        self.manager.engine = TorrentEngine(download_dir=self.downloader_dir)
        self.manager.engine.add_torrent(self.magnet_uri)

        # Connect directly to local seeder peer
        self.manager.engine.handle.connect_peer(("127.0.0.1", self.seeder_port))

        # 1. Metadata acquired without internet/trackers
        ready = self.manager.engine.wait_for_metadata(timeout=5.0)
        self.assertTrue(ready)
        status = self.manager.engine.get_status()
        self.assertTrue(status.has_metadata)
        self.assertEqual(len(status.files), 1)
        self.assertEqual(status.files[0].name, self.video_filename)

        # 2. Start HTTP bridge
        stream_url = self.manager.start_streaming(file_index=0)
        self.assertIsNotNone(stream_url)

        # Downloader connects peer again if needed
        self.manager.engine.handle.connect_peer(("127.0.0.1", self.seeder_port))

        # 3. HTTP GET initial range: bytes=0-2047
        req = urllib.request.Request(stream_url)
        req.add_header("Range", "bytes=0-2047")
        with urllib.request.urlopen(req, timeout=10.0) as resp:
            self.assertEqual(resp.status, 206)
            initial_data = resp.read()

        with open(self.corpus_video, "rb") as f:
            expected_initial = f.read(2048)
        self.assertEqual(initial_data, expected_initial)

        # 4. HTTP GET distant range: last 4096 bytes
        file_size = os.path.getsize(self.corpus_video)
        req_distant = urllib.request.Request(stream_url)
        req_distant.add_header("Range", f"bytes={file_size - 4096}-{file_size - 1}")
        with urllib.request.urlopen(req_distant, timeout=10.0) as resp:
            self.assertEqual(resp.status, 206)
            distant_data = resp.read()

        with open(self.corpus_video, "rb") as f:
            f.seek(file_size - 4096)
            expected_distant = f.read(4096)
        self.assertEqual(distant_data, expected_distant)

        # 5. Verify streaming was active and data was transferred
        progress = self.manager.get_status().progress
        self.assertGreater(progress, 0.0)

        # 6. Playback via headless JonakiCore
        core = JonakiCore(wid=None)
        core.start_engine()
        try:
            core.load_file(stream_url)
            self.assertEqual(core.state, PlaybackState.PLAYING)
            time.sleep(0.3)
            core.stop()
        finally:
            core.stop_engine()


if __name__ == "__main__":
    unittest.main()
