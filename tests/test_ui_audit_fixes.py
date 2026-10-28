"""
Unit tests covering UI audit fixes across JonakiPlayer UI modules:
- ContextMenu: safe popup on None/keyboard event, CMD_VIDEO_STRETCH dispatch, checkmark on disabled streams
- ControlBox: tab selection, signal loop prevention, live sync from player, shader checkboxes
- SkinEngine: default controls initialization when DSF missing, NaN/Inf time formatting, hit_testing
- MainWindow: Alt+F4 pass-through, Alt+arrows handling, audio filter reset, playback position save
- SubtitleTranslator: thread-safe caching
"""

import unittest
import os
import sys
import math
import threading
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
from gi.repository import Gtk, Gdk

from ui.context_menu import PotContextMenu
from ui.control_box import ControlBoxDialog
from ui.skin_engine import PotSkinEngine, SkinButton
from ui.main_window import JonakiMainWindow
from subtitle.translator import SubtitleTranslator


class TestContextMenuAuditFixes(unittest.TestCase):
    def setUp(self):
        self.mock_dispatcher = MagicMock()
        self.menu = PotContextMenu(self.mock_dispatcher)

    def test_popup_with_none_event(self):
        """Verify popup(event=None) does not raise AttributeError or crash."""
        try:
            self.menu.popup(event=None, core=None)
        except Exception as e:
            self.fail(f"popup(event=None) raised exception: {e}")

    def test_stretch_menu_command(self):
        """Verify 'Stretch to Window' item in aspect menu dispatches CMD_VIDEO_STRETCH."""
        stretch_item = None
        for item in self.menu.aspect_menu.get_children():
            if isinstance(item, Gtk.MenuItem) and "Stretch to Window" in (item.get_label() or ""):
                stretch_item = item
                break
        self.assertIsNotNone(stretch_item, "Stretch to Window menu item not found in aspect_menu")
        stretch_item.activate()
        self.mock_dispatcher.assert_called_with("CMD_VIDEO_STRETCH", None)

    def test_disabled_stream_checkmark(self):
        """Verify Disable Audio and Disable Subtitles show checkmarks when current track is disabled."""
        mock_core = MagicMock()
        mock_core.get_audio_tracks.return_value = [{"id": 1, "title": "Track 1"}]
        mock_core.get_current_audio_track_id.return_value = None
        mock_core.get_subtitle_tracks.return_value = [{"id": 1, "title": "Sub 1"}]
        mock_core.get_current_subtitle_track_id.return_value = None
        mock_core.get_current_secondary_subtitle_track_id.return_value = None

        self.menu.refresh_dynamic_menus(mock_core)

        # In audio_streams_menu, the "Disable Audio" item is appended last
        audio_items = self.menu.audio_streams_menu.get_children()
        disable_audio_item = [it for it in audio_items if "Disable Audio" in (it.get_label() or "")][0]
        self.assertTrue(disable_audio_item.get_label().startswith("✓ "))

        # In sub_streams_menu, the "Disable Subtitles" item is appended last
        sub_items = self.menu.sub_streams_menu.get_children()
        disable_sub_item = [it for it in sub_items if "Disable Subtitles" in (it.get_label() or "")][0]
        self.assertTrue(disable_sub_item.get_label().startswith("✓ "))


class TestControlBoxAuditFixes(unittest.TestCase):
    def setUp(self):
        self.mock_player = MagicMock()
        self.mock_player.equalizer.get_band.return_value = 0.0
        self.mock_player.equalizer.current_preset = "Default / Flat"
        self.mock_player.equalizer.enabled = False
        self.mock_player.dsp.normalizer_enabled = False
        self.mock_player.shader_mgr.brightness = 0
        self.mock_player.shader_mgr.contrast = 0
        self.mock_player.shader_mgr.saturation = 0
        self.mock_player.shader_mgr.hue = 0
        self.mock_player.shader_mgr.active_shaders = set()
        self.mock_player.sub_mgr.sync_offset_sec = 0.0
        self.mock_player.sub_mgr.font_size = 24
        self.mock_player.sub_mgr.translation_enabled = False
        self.mock_player.core.speed = 1.0

        self.dialog = ControlBoxDialog(self.mock_player)
        self.dialog.show_all()

    def tearDown(self):
        self.dialog.destroy()

    def test_select_tab(self):
        """Verify select_tab changes the notebook current page."""
        self.dialog.select_tab(0)
        self.assertEqual(self.dialog.notebook.get_current_page(), 0)
        self.dialog.select_tab(1)
        self.assertEqual(self.dialog.notebook.get_current_page(), 1)
        self.dialog.select_tab(2)
        self.assertEqual(self.dialog.notebook.get_current_page(), 2)

    def test_updating_controls_flag_prevents_signals(self):
        """Verify self._updating_controls suppresses redundant player calls on reset."""
        self.dialog._updating_controls = True
        self.dialog._on_color_changed(None)
        self.mock_player.core.set_video_colors.assert_not_called()

    def test_subtitle_sync_slider_updates_sub_mgr(self):
        """Verify sync slider updates sub_mgr.sync_offset_sec and calls set_subtitle_sync."""
        self.dialog._updating_controls = False
        self.dialog.sync_scale.set_value(1.5)
        self.assertEqual(self.mock_player.sub_mgr.sync_offset_sec, 1.5)
        self.mock_player.set_subtitle_sync.assert_called_with(1.5)


class TestSkinEngineAuditFixes(unittest.TestCase):
    def test_missing_dsf_initializes_default_controls(self):
        """Verify missing DSF file does not leave buttons as None."""
        engine = PotSkinEngine(dsf_path="/nonexistent/skin/path.dsf")
        self.assertIsNotNone(engine.btn_play)
        self.assertIsNotNone(engine.btn_pause)
        self.assertIsNotNone(engine.btn_stop)
        self.assertIsNotNone(engine.btn_prev)
        self.assertIsNotNone(engine.btn_next)
        self.assertIsNotNone(engine.btn_open)

    def test_format_time_nan_and_inf(self):
        """Verify _format_time handles None, NaN, and Inf safely."""
        engine = PotSkinEngine()
        self.assertEqual(engine._format_time(None), "00:00")
        self.assertEqual(engine._format_time(float("nan")), "00:00")
        self.assertEqual(engine._format_time(float("inf")), "00:00")
        self.assertEqual(engine._format_time(-5.0), "00:00")
        self.assertEqual(engine._format_time(3665.0), "01:01:05")

    def test_hit_testing_play_pause(self):
        """Verify hit_test returns btn_pause when playing and btn_play when paused."""
        engine = PotSkinEngine()
        engine.layout(800, 600)
        # btn_play and btn_pause are at (0, btn_y, 41, 40)
        hit_when_playing = engine.hit_test(10, engine.btn_pause.rect[1] + 10, is_playing=True)
        self.assertEqual(hit_when_playing, engine.btn_pause)

        hit_when_paused = engine.hit_test(10, engine.btn_play.rect[1] + 10, is_playing=False)
        self.assertEqual(hit_when_paused, engine.btn_play)


class TestTranslatorThreadSafety(unittest.TestCase):
    def test_concurrent_cache_access(self):
        """Verify thread-safe reading and writing to translation cache."""
        translator = SubtitleTranslator()
        errors = []

        with patch.object(translator, "_translate_google", side_effect=lambda text, *args, **kwargs: f"translated_{text}"):
            def worker(thread_id):
                try:
                    for i in range(100):
                        text = f"line_{i % 10}"
                        translator.translate(text, "en", "es")
                except Exception as e:
                    errors.append(e)

            threads = [threading.Thread(target=worker, args=(t,)) for t in range(5)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

        self.assertEqual(len(errors), 0, f"Thread safety errors occurred: {errors}")


class TestMainWindowAuditFixes(unittest.TestCase):
    def setUp(self):
        with patch("ui.main_window.JonakiCore"):
            self.win = JonakiMainWindow()
        self.win.core.position = 0.0

    def tearDown(self):
        self.win.destroy()

    def test_alt_f4_passes_through(self):
        """Verify Alt+F4 returns False so the window manager closes the window."""
        event = MagicMock()
        event.keyval = Gdk.KEY_F4
        event.state = Gdk.ModifierType.MOD1_MASK  # Alt
        handled = self.win._on_key_press(self.win, event)
        self.assertFalse(handled)

    def test_f4_stops_playback_when_not_alt(self):
        """Verify F4 without Alt calls CMD_MEDIA_CLOSE."""
        event = MagicMock()
        event.keyval = Gdk.KEY_F4
        event.state = 0
        with patch.object(self.win, "handle_command") as mock_cmd:
            handled = self.win._on_key_press(self.win, event)
            self.assertTrue(handled)
            mock_cmd.assert_called_with("CMD_MEDIA_CLOSE")

    def test_apply_audio_filters_when_disabled(self):
        """Verify apply_audio_filters zeroes out equalizer bands when equalizer is disabled."""
        self.win.dsp.enhancement_enabled = False
        self.win.equalizer.enabled = False
        self.win.core.equalizer_bands = [5.0] * 10
        self.win.apply_audio_filters()
        self.assertEqual(self.win.core.equalizer_bands, [0.0] * 10)
        self.win.core.set_property.assert_called_with("af", "")

    def test_save_current_position_helper(self):
        """Verify _save_current_position saves to media_db when position > 5.0."""
        self.win.core.current_file = "/path/to/movie.mp4"
        self.win.core.position = 120.5
        self.win.core.duration = 3600.0
        self.win.core.current_title = "Movie"
        with patch.object(self.win.db, "save_playback_position") as mock_save:
            self.win._save_current_position()
            mock_save.assert_called_with(
                "/path/to/movie.mp4",
                120.5,
                duration=3600.0,
                title="Movie"
            )


if __name__ == "__main__":
    unittest.main()
