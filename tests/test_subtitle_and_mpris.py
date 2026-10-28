"""
Unit tests for Online Subtitle Search, AI Translation, and MPRIS2 D-Bus service.
"""

import unittest
import os
import sys
import tempfile
import gzip
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from subtitle.online_search import compute_opensubtitles_hash, SubtitleSearchClient
from subtitle.translator import SubtitleTranslator
from core.mpris import MPRIS2Service, MPRIS_INTROSPECTION_XML
from core.engine import PlaybackState
import gi
gi.require_version('Gio', '2.0')
gi.require_version('Gtk', '3.0')
from gi.repository import Gio, GLib, Gtk


class TestSubtitleAndMPRIS(unittest.TestCase):
    def test_opensubtitles_hash_small_file(self):
        # Files smaller than 128KB should return None
        with tempfile.NamedTemporaryFile(delete=False) as tf:
            tf.write(b"Too small")
            tf_path = tf.name

        try:
            self.assertIsNone(compute_opensubtitles_hash(tf_path))
        finally:
            if os.path.exists(tf_path):
                os.remove(tf_path)

    def test_opensubtitles_hash_valid_file(self):
        # Generate exactly 200KB dummy file with known bytes
        size = 200 * 1024
        with tempfile.NamedTemporaryFile(delete=False) as tf:
            tf.write(b"\x01" * size)
            tf_path = tf.name

        try:
            h = compute_opensubtitles_hash(tf_path)
            self.assertIsNotNone(h)
            self.assertEqual(len(h), 16)
        finally:
            if os.path.exists(tf_path):
                os.remove(tf_path)

    def test_subtitle_download_and_gzip_decompression(self):
        client = SubtitleSearchClient()
        test_content = b"1\n00:00:01,000 --> 00:00:04,000\nHello World PotPlayer\n"
        compressed = gzip.compress(test_content)

        with tempfile.NamedTemporaryFile(suffix=".srt", delete=False) as tf:
            dest_file = tf.name

        try:
            with patch("urllib.request.urlopen") as mock_urlopen:
                mock_resp = MagicMock()
                mock_resp.read.return_value = compressed
                mock_resp.__enter__.return_value = mock_resp
                mock_urlopen.return_value = mock_resp

                ok = client.download_subtitle("http://example.com/sub.gz", dest_file)
                self.assertTrue(ok)
                self.assertTrue(os.path.exists(dest_file))
                with open(dest_file, "rb") as f:
                    decompressed = f.read()
                self.assertEqual(decompressed, test_content)
        finally:
            if os.path.exists(dest_file):
                os.remove(dest_file)

    def test_subtitle_translator_lru_cache(self):
        translator = SubtitleTranslator(max_cache_size=3)
        translator._cache[("One", "auto", "en")] = "Un"
        translator._cache[("Two", "auto", "en")] = "Deux"
        translator._cache[("Three", "auto", "en")] = "Trois"

        # Cached lookup should return immediately without HTTP and mark accessed
        res = translator.translate("One", src_lang="auto", dst_lang="en")
        self.assertEqual(res, "Un")

        # Mock network translate for adding 4th item
        with patch.object(translator, "_translate_google", return_value="Quatre"):
            translator.translate("Four", src_lang="auto", dst_lang="en")

        # Cache size must not exceed max_cache_size (3)
        self.assertEqual(len(translator._cache), 3)
        # "Two" was the least recently used, so it must be evicted
        self.assertNotIn(("Two", "auto", "en"), translator._cache)
        # "One", "Three", and "Four" must be present
        self.assertIn(("One", "auto", "en"), translator._cache)
        self.assertIn(("Three", "auto", "en"), translator._cache)
        self.assertIn(("Four", "auto", "en"), translator._cache)

    def test_mpris2_introspection_xml(self):
        node = Gio.DBusNodeInfo.new_for_xml(MPRIS_INTROSPECTION_XML)
        self.assertIsNotNone(node)
        root_iface = node.lookup_interface("org.mpris.MediaPlayer2")
        self.assertIsNotNone(root_iface)
        player_iface = node.lookup_interface("org.mpris.MediaPlayer2.Player")
        self.assertIsNotNone(player_iface)

        # Verify critical methods exist
        methods = [m.name for m in player_iface.methods]
        self.assertIn("PlayPause", methods)
        self.assertIn("Play", methods)
        self.assertIn("Pause", methods)
        self.assertIn("Stop", methods)
        self.assertIn("Next", methods)
        self.assertIn("Previous", methods)
        self.assertIn("Seek", methods)

    def test_mpris2_service_property_getters(self):
        mock_win = MagicMock()
        mock_win.is_fullscreen = False
        mock_win.core.state = PlaybackState.PLAYING
        mock_win.core.volume = 80.0
        mock_win.core.position = 12.5
        mock_win.core.duration = 120.0
        mock_win.core.current_file = "/media/sample.mp4"
        mock_win.core.current_title = "sample.mp4"
        mock_win.core.speed = 1.0

        service = MPRIS2Service(mock_win)

        # Root interface properties
        ident = service._on_root_get_property(None, None, None, None, "Identity")
        self.assertEqual(ident.get_string(), "Jonaki")

        can_quit = service._on_root_get_property(None, None, None, None, "CanQuit")
        self.assertTrue(can_quit.get_boolean())

        # Player interface properties
        status = service._on_player_get_property(None, None, None, None, "PlaybackStatus")
        self.assertEqual(status.get_string(), "Playing")

        vol = service._on_player_get_property(None, None, None, None, "Volume")
        self.assertAlmostEqual(vol.get_double(), 0.8)

        pos = service._on_player_get_property(None, None, None, None, "Position")
        self.assertEqual(pos.get_int64(), 12500000)

        meta = service._on_player_get_property(None, None, None, None, "Metadata")
        self.assertIsNotNone(meta)

    def test_mpris2_nan_infinity_safety_and_notrack(self):
        # BUG 4.1 & BUG 4.3: Live stream NaN/inf values must not crash, and stopped state reports NoTrack
        mock_win = MagicMock()
        mock_win.core.position = float('nan')
        mock_win.core.duration = float('inf')
        mock_win.core.current_file = None

        service = MPRIS2Service(mock_win)
        pos = service._on_player_get_property(None, None, None, None, "Position")
        self.assertEqual(pos.get_int64(), 0)

        meta = service._build_metadata_variant()
        self.assertIn("mpris:trackid", meta.unpack())
        self.assertEqual(meta.unpack()["mpris:trackid"], "/org/mpris/MediaPlayer2/TrackList/NoTrack")

    def test_mpris2_url_rfc3986_encoding(self):
        # BUG 4.2: Paths with special characters (#, spaces) must be encoded per RFC 3986
        mock_win = MagicMock()
        mock_win.core.position = 10.0
        mock_win.core.duration = 60.0
        mock_win.core.current_file = "/media/My Movies/Episode #1.mkv"
        mock_win.core.current_title = "Episode #1.mkv"

        service = MPRIS2Service(mock_win)
        meta = service._build_metadata_variant()
        meta_dict = meta.unpack()
        self.assertIn("xesam:url", meta_dict)
        url_str = meta_dict["xesam:url"]
        self.assertTrue(url_str.startswith("file://"))
        self.assertIn("%23", url_str)  # # should be %23
        self.assertNotIn(" ", url_str)  # space should be %20

    def test_mpris2_set_position_and_loop_status(self):
        # BUG 4.4 & BUG 4.5: SetPosition bounds check and LoopStatus property setter/getter
        mock_win = MagicMock()
        mock_win.core.duration = 100.0
        mock_win.core.get_property.side_effect = lambda k: "inf" if k == "loop-file" else "no"

        service = MPRIS2Service(mock_win)

        # LoopStatus getter
        loop = service._on_player_get_property(None, None, None, None, "LoopStatus")
        self.assertEqual(loop.get_string(), "Track")

        # LoopStatus setter
        ok = service._on_player_set_property(None, None, None, None, "LoopStatus", GLib.Variant("s", "Playlist"))
        self.assertTrue(ok)
        mock_win.core.set_property.assert_any_call("loop-playlist", "inf")

        # SetPosition with wrong track id is ignored
        mock_win.core.seek_absolute.reset_mock()
        service._on_player_method_call(None, None, None, None, "SetPosition",
                                       GLib.Variant("(ox)", ("/org/mpris/MediaPlayer2/OtherTrack", 50000000)),
                                       MagicMock())
        mock_win.core.seek_absolute.assert_not_called()

        # SetPosition with valid track id seeks
        service._on_player_method_call(None, None, None, None, "SetPosition",
                                       GLib.Variant("(ox)", ("/org/mpris/MediaPlayer2/CurrentTrack", 50000000)),
                                       MagicMock())
        mock_win.core.seek_absolute.assert_called_with(50.0)

    def test_subtitle_search_dialog_ui(self):
        from ui.subtitle_search_dialog import SubtitleSearchDialog
        callback_called = []
        dialog = SubtitleSearchDialog(None, None, lambda p: callback_called.append(p))
        self.assertIsNotNone(dialog)
        self.assertEqual(dialog.status_label.get_text(), "Ready")
        self.assertEqual(len(dialog.liststore), 0)

        # BUG-006: Verify style context provider is scoped to dialog
        style_ctx = dialog.get_style_context()
        self.assertIsNotNone(style_ctx)

        # Simulate search results finished
        results = [
            {"title": "Movie Subtitle 1080p", "language": "English", "format": "srt", "rating": "9.5", "download_url": "http://example.com/1.srt"}
        ]
        dialog._on_search_finished(results, "")
        self.assertEqual(len(dialog.liststore), 1)
        self.assertEqual(dialog.liststore[0][0], "Movie Subtitle 1080p")
        self.assertIn("Found 1 subtitle", dialog.status_label.get_text())

        # Test row selection enables download button
        self.assertFalse(dialog.download_btn.get_sensitive())
        dialog.treeview.get_selection().select_path(Gtk.TreePath.new_first())
        self.assertTrue(dialog.download_btn.get_sensitive())

        # BUG-049: Test download finished triggers response and callback cleanly
        with tempfile.NamedTemporaryFile(suffix=".srt", delete=False) as tf:
            tf.write(b"1\n00:00:01,000 --> 00:00:02,000\nTest\n")
            sub_path = tf.name

        try:
            responses = []
            dialog.connect("response", lambda d, r: responses.append(r))
            dialog._on_download_finished(True, sub_path, "Movie Subtitle 1080p")
            self.assertEqual(callback_called, [sub_path])
            self.assertEqual(responses, [Gtk.ResponseType.OK])
        finally:
            if os.path.exists(sub_path):
                os.remove(sub_path)
            dialog.destroy()

    def test_mpris2_methods_and_signals(self):
        # BUG 7.4: Test coverage for MPRIS2 methods, property setters, and signals
        mock_win = MagicMock()
        mock_win.is_fullscreen = False
        mock_core = MagicMock()
        mock_win.core = mock_core
        mock_core.state = PlaybackState.PLAYING
        mock_core.duration = 100.0
        mock_core.position = 10.0
        mock_core.current_file = "/media/test.mp4"
        mock_core.current_title = "test.mp4"
        mock_core.speed = 1.0
        mock_core.volume = 80.0

        service = MPRIS2Service(mock_win)
        mock_inv = MagicMock()

        # Root methods: Raise and Quit
        service._on_root_method_call(None, None, None, None, "Raise", None, mock_inv)
        mock_win.present.assert_called_once()
        mock_inv.return_value.assert_called_with(None)

        mock_inv.reset_mock()
        service._on_root_method_call(None, None, None, None, "Quit", None, mock_inv)
        mock_win.handle_command.assert_called_with("CMD_APP_EXIT")
        mock_inv.return_value.assert_called_with(None)

        # Root property: Fullscreen setter
        res = service._on_root_set_property(None, None, None, None, "Fullscreen", GLib.Variant("b", True))
        self.assertTrue(res)
        mock_win.toggle_fullscreen.assert_called_once()

        # Player methods: Play, Pause, PlayPause, Stop, Next, Previous, Seek, OpenUri
        for method, mock_target in [
            ("Play", mock_core.play),
            ("Pause", mock_core.pause),
            ("Stop", mock_core.stop),
            ("Next", mock_win.play_next),
            ("Previous", mock_win.play_prev),
            ("PlayPause", mock_win.toggle_play_pause),
        ]:
            mock_inv.reset_mock()
            mock_target.reset_mock()
            service._on_player_method_call(None, None, None, None, method, None, mock_inv)
            mock_target.assert_called_once()
            mock_inv.return_value.assert_called_with(None)

        # Seek: 15 seconds forward (15,000,000 microseconds)
        mock_inv.reset_mock()
        service._on_player_method_call(None, None, None, None, "Seek", GLib.Variant("(x)", (15000000,)), mock_inv)
        mock_core.seek_relative.assert_called_with(15.0)

        # OpenUri
        mock_inv.reset_mock()
        service._on_player_method_call(None, None, None, None, "OpenUri", GLib.Variant("(s)", ("file:///media/test.mp4",)), mock_inv)
        mock_win.play_file.assert_called_with("file:///media/test.mp4")

        # Player property setters: Volume and Rate
        service._on_player_set_property(None, None, None, None, "Volume", GLib.Variant("d", 0.75))
        mock_core.set_volume.assert_called_with(75.0)

        service._on_player_set_property(None, None, None, None, "Rate", GLib.Variant("d", 1.25))
        mock_core.set_speed.assert_called_with(1.25)

        # Signal notification
        mock_conn = MagicMock()
        service.connection = mock_conn
        service.notify_playback_changed()
        mock_conn.emit_signal.assert_called_once()


if __name__ == "__main__":
    unittest.main()
