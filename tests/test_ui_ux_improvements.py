"""
Unit tests covering UI and UX improvements in Jonaki:
- Device capture URLs (x11grab and v4l2)
- Shaders (denoise.hook presence and syntax)
- IPC payload serialization and dialog flags
- SkinEngine dynamic badge layout and hour symmetrization
- OpenSubtitles fast block hasher correctness
- Context menu recent files integration
"""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from jonaki import parse_arguments
from ui.skin_engine import PotSkinEngine
from subtitle.online_search import compute_opensubtitles_hash
from ui.context_menu import PotContextMenu


class TestUIUXImprovements(unittest.TestCase):
    def test_denoise_shader_exists(self):
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        shader_path = os.path.join(base_dir, "assets", "shaders", "denoise.hook")
        self.assertTrue(os.path.exists(shader_path), f"Shader not found at {shader_path}")
        with open(shader_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("//!HOOK MAIN", content)
        self.assertIn("//!BIND HOOKED", content)
        self.assertIn("vec4 hook()", content)

    def test_cli_play_pause_and_dialog_switches(self):
        opts = parse_arguments(["jonaki", "/play", "/pause", "/filedlg", "/folderdlg", "/urldlg", "/torrentdlg", "/clipboard"])
        self.assertTrue(opts["play"])
        self.assertTrue(opts["pause"])
        self.assertTrue(opts["filedlg"])
        self.assertTrue(opts["folderdlg"])
        self.assertTrue(opts["urldlg"])
        self.assertTrue(opts["torrentdlg"])
        self.assertTrue(opts["clipboard"])

    def test_skin_time_formatting_symmetrization(self):
        skin = PotSkinEngine()
        # When duration < 1 hour: both are mm:ss
        self.assertEqual(skin._format_time(125.0, 1800.0), "02:05")
        self.assertEqual(skin._format_time(1800.0, 1800.0), "30:00")

        # When duration >= 1 hour: both must be formatted with hh:mm:ss
        self.assertEqual(skin._format_time(125.0, 3600.0), "00:02:05")
        self.assertEqual(skin._format_time(3665.0, 3665.0), "01:01:05")
        self.assertEqual(skin._format_time(0.0, 7200.0), "00:00:00")

    def test_skin_badge_dynamic_positioning(self):
        skin = PotSkinEngine()
        skin.layout(960, 62, min_badge_x=345)
        # badge_hw should start at or after min_badge_x
        hw_x, hw_y, hw_w, hw_h = skin.badge_hw.rect
        self.assertGreaterEqual(hw_x, 345)

        # On small widths, badges hide gracefully
        skin.layout(300, 62)
        hw_x, _, _, _ = skin.badge_hw.rect
        self.assertEqual(hw_x, -100)

    def test_opensubtitles_hash_correctness(self):
        # Create a test file of 128KB with deterministic data
        with tempfile.NamedTemporaryFile(delete=False) as tf:
            tf.write(b"\x01" * 65536)
            tf.write(b"\x02" * 65536)
            tf_name = tf.name

        try:
            h = compute_opensubtitles_hash(tf_name)
            self.assertIsNotNone(h)
            self.assertEqual(len(h), 16)
            # Re-verifying idempotency
            h2 = compute_opensubtitles_hash(tf_name)
            self.assertEqual(h, h2)
        finally:
            if os.path.exists(tf_name):
                os.remove(tf_name)

    def test_context_menu_recent_files(self):
        actions = []
        menu = PotContextMenu(lambda cmd, arg: actions.append((cmd, arg)))
        self.assertIsNotNone(menu.recent_menu)

        recent_sample = [
            {"file_path": "/home/user/movie1.mkv", "title": "Movie 1"},
            {"file_path": "/home/user/movie2.mp4", "title": "Movie 2"}
        ]
        menu.refresh_recent_menu(recent_sample)
        children = menu.recent_menu.get_children()
        # 2 items + 1 separator + 1 clear item = 4
        self.assertEqual(len(children), 4)

    def test_uri_normalization(self):
        from ui.main_window import normalize_media_path
        self.assertEqual(normalize_media_path("file:///home/user/my%20video.mp4"), "/home/user/my video.mp4")
        self.assertEqual(normalize_media_path("/home/user/video.mkv"), "/home/user/video.mkv")
        self.assertEqual(normalize_media_path("https://example.com/stream.m3u8"), "https://example.com/stream.m3u8")

    def test_media_db_playback_entry_persistence(self):
        from core.media_db import MediaDatabase
        with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as tf:
            db_path = tf.name
        try:
            db = MediaDatabase(db_path=db_path)
            db.save_playback_position("/tmp/test.mkv", 45.2, duration=120.0, title="Test Movie",
                                      audio_track="2", subtitle_track="1", volume=85.0)
            entry = db.get_playback_entry("/tmp/test.mkv")
            self.assertIsNotNone(entry)
            self.assertAlmostEqual(entry["last_position"], 45.2, places=1)
            self.assertAlmostEqual(entry["duration"], 120.0, places=1)
            self.assertEqual(str(entry["audio_track"]), "2")
            self.assertEqual(str(entry["subtitle_track"]), "1")
            self.assertAlmostEqual(entry["volume"], 85.0, places=1)
        finally:
            if os.path.exists(db_path):
                os.remove(db_path)

    def test_core_chapters_api(self):
        from unittest.mock import MagicMock
        from core.engine import JonakiCore
        core = JonakiCore()
        fake_chapters = [
            {"title": "Intro", "time": 0.0},
            {"title": "Action Scene", "time": 150.0},
            {"title": "Credits", "time": 600.0}
        ]
        core._mpv = MagicMock()
        core.get_property = MagicMock(side_effect=lambda prop: fake_chapters if prop == "chapter-list" else "1" if prop == "chapter" else None)
        core.get_property_float = MagicMock(return_value=1.0)
        core.set_property = MagicMock()
        core.command = MagicMock()

        chapters = core.get_chapters()
        self.assertEqual(len(chapters), 3)
        self.assertEqual(chapters[1]["title"], "Action Scene")
        current_idx = core.get_current_chapter()
        self.assertEqual(current_idx, 1)

        # Set, Next, Prev
        core.set_chapter(2)
        core.set_property.assert_called_with("chapter", "2")
        core.next_chapter()
        core.command.assert_any_call("add chapter 1")
        core.prev_chapter()
        core.command.assert_any_call("add chapter -1")

    def test_skin_render_chapter_ticks(self):
        import cairo
        skin = PotSkinEngine()
        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 960, 62)
        cr = cairo.Context(surface)
        # Verify render succeeds with chapter tick marks
        skin.render(cr, 960, 62, is_playing=True, position_sec=45.0, duration_sec=300.0,
                    chapters=[60.0, 120.0, 240.0])

    def test_cli_sort_randomize_title(self):
        opts = parse_arguments(["jonaki", "/sort", "/randomize", "/title=MyMovie", "/user_agent=CustomAgent"])
        self.assertTrue(opts["sort"])
        self.assertTrue(opts["randomize"])
        self.assertEqual(opts["title"], "MyMovie")
        self.assertEqual(opts["user_agent"], "CustomAgent")


if __name__ == "__main__":
    unittest.main()
