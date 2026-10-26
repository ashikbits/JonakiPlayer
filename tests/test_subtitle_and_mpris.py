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

        dest_file = tempfile.mktemp(suffix=".srt")

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

        if os.path.exists(dest_file):
            os.remove(dest_file)

    def test_subtitle_translator_lru_cache(self):
        translator = SubtitleTranslator()
        translator._cache[("Hello", "auto", "en")] = "Bonjour"
        # Cached lookup should return immediately without HTTP
        res = translator.translate("Hello", src_lang="auto", dst_lang="en")
        self.assertEqual(res, "Bonjour")

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

    def test_subtitle_search_dialog_ui(self):
        from ui.subtitle_search_dialog import SubtitleSearchDialog
        callback_called = []
        dialog = SubtitleSearchDialog(None, None, lambda p: callback_called.append(p))
        self.assertIsNotNone(dialog)
        self.assertEqual(dialog.status_label.get_text(), "Ready")
        self.assertEqual(len(dialog.liststore), 0)

        # Simulate search results finished
        results = [
            {"title": "Movie Subtitle 1080p", "language": "English", "format": "srt", "rating": "9.5", "download_url": "http://example.com/1.srt"}
        ]
        dialog._on_search_finished(results, "")
        self.assertEqual(len(dialog.liststore), 1)
        self.assertEqual(dialog.liststore[0][0], "Movie Subtitle 1080p")
        self.assertIn("Found 1 subtitle", dialog.status_label.get_text())
        dialog.destroy()


if __name__ == "__main__":
    unittest.main()
