"""
Comprehensive automated test suite for Jonaki Player (PotPlayer Linux) UI & Navigation QA audit.

Scope:
- Phase 2.C: User Interface and Controls (DSF skin buttons, sliders, keyboard shortcuts, window lifecycle,
  fullscreen transition, aspect ratio stretching, cursor auto-hide, OSD overlay, Tech Info HUD).
- Phase 2.D: Playlist and Media Navigation (Add, remove, reorder, duplicate handling, missing files,
  search/filter, sort, shuffle, next/previous boundaries, playlist window F8/F12, Control Box F6,
  Media Info Ctrl+F1, Subtitle Search Ctrl+Alt+S, About F1).
- Context Menu: Right-click popup, dynamic audio track list, dynamic subtitle track list, dual subtitles,
  aspect ratio menu, video orientation menu, pixel shaders.
"""

import unittest
import os
import sys
import math
import time
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
from gi.repository import Gtk, Gdk, GLib
import cairo

from ui.skin_engine import PotSkinEngine, SkinButton, SkinSlider, clean_codec_name
from ui.main_window import JonakiMainWindow
from ui.playlist_view import PlaylistWindow
from ui.control_box import ControlBoxDialog
from ui.context_menu import PotContextMenu
from ui.osd_overlay import OSDOverlay
from ui.media_info_dialog import MediaInfoDialog
from core.engine import PlaybackState


class TestSkinEngineControls(unittest.TestCase):
    """Phase 2.C: DSF Skin Engine Controls & Hit-Testing Tests."""

    def setUp(self):
        self.skin = PotSkinEngine()
        self.skin.layout(960, 62)

    def test_TC_SKIN_01_all_visible_buttons_present(self):
        """TC-SKIN-01: Verify all expected DSF skin buttons are initialized."""
        expected_cmds = [
            "CMD_MEDIA_PLAY",
            "CMD_MEDIA_PAUSE",
            "CMD_MEDIA_CLOSE",
            "ID_PLAYBACK_5SEC_BACK",
            "ID_PLAYBACK_5SEC_FORW",
            "ID_BASE_OPEN",
            "ID_AUDIO_MUTE",
            "CMD_POPUPMENU_STREAM_SELECT",
            "ID_PLAYLIST_WINDOW",
            "ID_CONTROL_BOX_WINDOW"
        ]
        actual_cmds = [b.cmd_id for b in self.skin.buttons]
        for cmd in expected_cmds:
            self.assertIn(cmd, actual_cmds, f"Expected button {cmd} missing from skin")

    def test_TC_SKIN_02_sliders_initialized(self):
        """TC-SKIN-02: Verify Seek and Volume sliders are initialized with valid dimensions."""
        self.assertIsNotNone(self.skin.timebar, "Timebar seek slider must not be None")
        self.assertIsNotNone(self.skin.volume_slider, "Volume slider must not be None")

        # Timebar bounds
        tx, ty, tw, th = self.skin.timebar.rect
        self.assertGreater(tw, 0)
        self.assertEqual(th, 10)

        # Volume slider bounds
        vx, vy, vw, vh = self.skin.volume_slider.rect
        self.assertGreater(vw, 0)
        self.assertEqual(vh, 10)
        self.assertAlmostEqual(self.skin.volume_slider.value, 0.8)

    def test_TC_SKIN_03_hit_testing_transport_buttons(self):
        """TC-SKIN-03: Hit testing for transport buttons respects playback state."""
        # When stopped/paused: Play button should be hit, Pause button skipped
        hit_play = self.skin.hit_test(self.skin.btn_play.rect[0] + 5, self.skin.btn_play.rect[1] + 5, is_playing=False)
        self.assertEqual(hit_play, self.skin.btn_play)

        # When playing: Pause button should be hit, Play button skipped
        hit_pause = self.skin.hit_test(self.skin.btn_pause.rect[0] + 5, self.skin.btn_pause.rect[1] + 5, is_playing=True)
        self.assertEqual(hit_pause, self.skin.btn_pause)

        # Stop, Prev, Next, Open
        hit_stop = self.skin.hit_test(self.skin.btn_stop.rect[0] + 5, self.skin.btn_stop.rect[1] + 5)
        self.assertEqual(hit_stop, self.skin.btn_stop)

        hit_prev = self.skin.hit_test(self.skin.btn_prev.rect[0] + 5, self.skin.btn_prev.rect[1] + 5)
        self.assertEqual(hit_prev, self.skin.btn_prev)

        hit_next = self.skin.hit_test(self.skin.btn_next.rect[0] + 5, self.skin.btn_next.rect[1] + 5)
        self.assertEqual(hit_next, self.skin.btn_next)

        hit_open = self.skin.hit_test(self.skin.btn_open.rect[0] + 5, self.skin.btn_open.rect[1] + 5)
        self.assertEqual(hit_open, self.skin.btn_open)

    def test_TC_SKIN_04_hit_testing_tool_buttons(self):
        """TC-SKIN-04: Hit testing for right tool buttons and mute button."""
        hit_mute = self.skin.hit_test(self.skin.btn_mute.rect[0] + 2, self.skin.btn_mute.rect[1] + 2)
        self.assertEqual(hit_mute, self.skin.btn_mute)

        hit_cbox = self.skin.hit_test(self.skin.btn_control_box.rect[0] + 2, self.skin.btn_control_box.rect[1] + 2)
        self.assertEqual(hit_cbox, self.skin.btn_control_box)

        hit_pl = self.skin.hit_test(self.skin.btn_playlist.rect[0] + 2, self.skin.btn_playlist.rect[1] + 2)
        self.assertEqual(hit_pl, self.skin.btn_playlist)

        hit_stream = self.skin.hit_test(self.skin.btn_stream.rect[0] + 2, self.skin.btn_stream.rect[1] + 2)
        self.assertEqual(hit_stream, self.skin.btn_stream)

    def test_TC_SKIN_05_hit_testing_sliders_vertical_tolerance(self):
        """TC-SKIN-05: Hit testing sliders has vertical tolerance (-3 to +4 px)."""
        tx, ty, tw, th = self.skin.timebar.rect
        # Exact top - 2px (within tolerance)
        self.assertEqual(self.skin.hit_test(tx + 10, ty - 2), self.skin.timebar)
        # Bottom + 3px (within tolerance)
        self.assertEqual(self.skin.hit_test(tx + 10, ty + th + 3), self.skin.timebar)
        # Far above (out of bounds)
        self.assertNotEqual(self.skin.hit_test(tx + 10, ty - 10), self.skin.timebar)

    def test_TC_SKIN_06_badges_hit_testing_and_dispatch(self):
        """TC-SKIN-06: Dynamic media badges hit testing."""
        # HW badge
        hw_x, hw_y, hw_w, hw_h = self.skin.badge_hw.rect
        self.assertGreater(hw_x, 0)
        hit_hw = self.skin.hit_test(hw_x + 2, hw_y + 2)
        self.assertEqual(hit_hw, self.skin.badge_hw)

        # HDR badge
        hdr_x, hdr_y, hdr_w, hdr_h = self.skin.badge_hdr.rect
        self.assertGreater(hdr_x, 0)
        hit_hdr = self.skin.hit_test(hdr_x + 2, hdr_y + 2)
        self.assertEqual(hit_hdr, self.skin.badge_hdr)

    def test_TC_SKIN_07_render_nan_and_zero_duration(self):
        """TC-SKIN-07: Rendering with zero, negative, NaN, and Inf duration/position."""
        surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, 800, 62)
        cr = cairo.Context(surf)

        # Zero duration
        try:
            self.skin.render(cr, 800, 62, is_playing=False, position_sec=0.0, duration_sec=0.0)
        except Exception as e:
            self.fail(f"render with duration=0.0 failed: {e}")

        # NaN duration and position
        try:
            self.skin.render(cr, 800, 62, is_playing=True, position_sec=float('nan'), duration_sec=float('nan'))
        except Exception as e:
            self.fail(f"render with NaN failed: {e}")

        # Inf duration and position
        try:
            self.skin.render(cr, 800, 62, is_playing=True, position_sec=float('inf'), duration_sec=float('inf'))
        except Exception as e:
            self.fail(f"render with Inf failed: {e}")

        # Negative position and duration
        try:
            self.skin.render(cr, 800, 62, is_playing=True, position_sec=-50.0, duration_sec=-10.0)
        except Exception as e:
            self.fail(f"render with negative time failed: {e}")

    def test_TC_SKIN_08_layout_narrow_panel(self):
        """TC-SKIN-08: Skin layout calculation on narrow window width (e.g. 300px)."""
        self.skin.layout(300, 62)
        self.assertGreaterEqual(self.skin.timebar.rect[2], 40, "Timebar should enforce minimum width")
        # On 300px width, min_parent_width for badges should hide them to prevent clipping
        for b in self.skin.badges:
            if b.min_parent_width > 300:
                self.assertEqual(b.rect[0], -100, f"Badge {b.label_text} should be hidden on 300px width")

    def test_TC_SKIN_09_fullscreen_button_presence(self):
        """TC-SKIN-09: Verify DEF-UI-01 fix: Fullscreen toggle button exists on skin."""
        cmds = [b.cmd_id for b in self.skin.buttons]
        has_fs_button = "CMD_FULLSCREEN" in cmds
        self.assertTrue(has_fs_button, "DEF-UI-01 verified: Fullscreen button is now present on skin")


class TestKeyboardShortcuts(unittest.TestCase):
    """Phase 2.C: Keyboard Shortcuts Dispatcher Tests."""

    def setUp(self):
        self.win = JonakiMainWindow()
        # Mock core methods
        self.win.core.play_pause = MagicMock()
        self.win.core.stop = MagicMock()
        self.win.core.seek_relative = MagicMock()
        self.win.core.adjust_volume = MagicMock()
        self.win.core.toggle_mute = MagicMock()
        self.win.core.set_speed = MagicMock()
        self.win.core.toggle_stretch = MagicMock(return_value="Stretch")
        self.win.core.cycle_audio_track = MagicMock()
        self.win.core.cycle_subtitle_track = MagicMock()
        self.win.core.cycle_secondary_subtitle_track = MagicMock()
        self.win.core.set_subtitle_delay = MagicMock()
        self.win.core.set_audio_delay = MagicMock()
        self.win.core.adjust_subtitle_pos = MagicMock(return_value=100)
        self.win.core.set_subtitle_font_size = MagicMock()
        self.win.core.set_video_colors = MagicMock()
        self.win.core.scale_video_height = MagicMock(return_value=1.05)
        self.win.core.scale_video_width = MagicMock(return_value=1.05)
        self.win.core.zoom_video = MagicMock(return_value=1.05)
        self.win.core.reset_video_dimensions = MagicMock()

    def tearDown(self):
        self.win.destroy()

    def _simulate_key(self, keyval: int, state: int = 0) -> bool:
        event = MagicMock()
        event.keyval = keyval
        event.state = state
        return self.win._on_key_press(self.win, event)

    def test_TC_KEY_01_space_play_pause(self):
        """TC-KEY-01: Space toggles play/pause."""
        ret = self._simulate_key(Gdk.KEY_space)
        self.assertTrue(ret)
        self.win.core.play_pause.assert_called_once()

    def test_TC_KEY_02_enter_fullscreen(self):
        """TC-KEY-02: Enter toggles fullscreen."""
        with patch.object(self.win, "toggle_fullscreen") as mock_fs:
            ret = self._simulate_key(Gdk.KEY_Return)
            self.assertTrue(ret)
            mock_fs.assert_called_once()

    def test_TC_KEY_03_ctrl_enter_stretch(self):
        """TC-KEY-03: Ctrl+Enter toggles video stretch."""
        ret = self._simulate_key(Gdk.KEY_Return, Gdk.ModifierType.CONTROL_MASK)
        self.assertTrue(ret)
        self.win.core.toggle_stretch.assert_called_once()

    def test_TC_KEY_04_esc_key(self):
        """TC-KEY-04: Esc exits fullscreen or stops playback."""
        # In fullscreen
        self.win.is_fullscreen = True
        with patch.object(self.win, "toggle_fullscreen") as mock_fs:
            ret = self._simulate_key(Gdk.KEY_Escape)
            self.assertTrue(ret)
            mock_fs.assert_called_once()

        # In windowed mode
        self.win.is_fullscreen = False
        ret = self._simulate_key(Gdk.KEY_Escape)
        self.assertTrue(ret)
        self.win.core.stop.assert_called_once()

    def test_TC_KEY_05_seek_shortcuts(self):
        """TC-KEY-05: Left/Right 5s, Ctrl+Left/Right 30s, Shift+Left/Right 60s, Ctrl+Alt 300s."""
        # 5s seek
        self._simulate_key(Gdk.KEY_Left)
        self.win.core.seek_relative.assert_called_with(-5.0)
        self._simulate_key(Gdk.KEY_Right)
        self.win.core.seek_relative.assert_called_with(5.0)

        # 30s seek (Ctrl)
        self._simulate_key(Gdk.KEY_Left, Gdk.ModifierType.CONTROL_MASK)
        self.win.core.seek_relative.assert_called_with(-30.0)
        self._simulate_key(Gdk.KEY_Right, Gdk.ModifierType.CONTROL_MASK)
        self.win.core.seek_relative.assert_called_with(30.0)

        # 60s seek (Shift)
        self._simulate_key(Gdk.KEY_Left, Gdk.ModifierType.SHIFT_MASK)
        self.win.core.seek_relative.assert_called_with(-60.0)
        self._simulate_key(Gdk.KEY_Right, Gdk.ModifierType.SHIFT_MASK)
        self.win.core.seek_relative.assert_called_with(60.0)

        # 300s seek (Ctrl+Alt)
        self._simulate_key(Gdk.KEY_Left, Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.MOD1_MASK)
        self.win.core.seek_relative.assert_called_with(-300.0)
        self._simulate_key(Gdk.KEY_Right, Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.MOD1_MASK)
        self.win.core.seek_relative.assert_called_with(300.0)

    def test_TC_KEY_06_volume_and_mute(self):
        """TC-KEY-06: Up/Down volume and M mute."""
        self._simulate_key(Gdk.KEY_Up)
        self.win.core.adjust_volume.assert_called_with(+2.0)
        self._simulate_key(Gdk.KEY_Down)
        self.win.core.adjust_volume.assert_called_with(-2.0)

        self._simulate_key(Gdk.KEY_m)
        self.win.core.toggle_mute.assert_called_once()

    def test_TC_KEY_07_preamp_boost_and_discrepancy(self):
        """TC-KEY-07: Shift+Up/Down PreAmp boost and discrepancy check with CMD_AUDIO_BOOST_UP."""
        initial_boost = self.win.dsp.audio_boost_db
        self._simulate_key(Gdk.KEY_Up, Gdk.ModifierType.SHIFT_MASK)
        self.assertEqual(self.win.dsp.audio_boost_db, initial_boost + 1.0)

        self._simulate_key(Gdk.KEY_Down, Gdk.ModifierType.SHIFT_MASK)
        self.assertEqual(self.win.dsp.audio_boost_db, initial_boost)

        # DEF-UI-03 verified: Shift+Up and context menu both cap at 24.0 dB
        self.win.dsp.audio_boost_db = 12.0
        self._simulate_key(Gdk.KEY_Up, Gdk.ModifierType.SHIFT_MASK)
        self.assertEqual(self.win.dsp.audio_boost_db, 13.0, "DEF-UI-03 verified: Shift+Up increments past 12.0 dB up to 24.0 dB")

        self.win.dsp.audio_boost_db = 24.0
        self._simulate_key(Gdk.KEY_Up, Gdk.ModifierType.SHIFT_MASK)
        self.assertEqual(self.win.dsp.audio_boost_db, 24.0, "Shift+Up caps at 24.0 dB")

        self.win.handle_command("CMD_AUDIO_BOOST_UP")
        self.assertEqual(self.win.dsp.audio_boost_db, 24.0, "CMD_AUDIO_BOOST_UP caps at 24.0 dB")

    def test_TC_KEY_08_audio_normalizer(self):
        """TC-KEY-08: Shift+N toggles dynamic audio normalizer."""
        init_state = self.win.dsp.normalizer_enabled
        ret = self._simulate_key(Gdk.KEY_n, Gdk.ModifierType.SHIFT_MASK)
        self.assertTrue(ret)
        self.assertEqual(self.win.dsp.normalizer_enabled, not init_state)

    def test_TC_KEY_09_audio_sync_shortcuts(self):
        r"""TC-KEY-09: Shift+[/] adjusts audio sync ±50ms, Shift+\ resets."""
        self.win.core.audio_delay_sec = 0.0
        self._simulate_key(Gdk.KEY_bracketleft, Gdk.ModifierType.SHIFT_MASK)
        self.win.core.set_audio_delay.assert_called_with(-0.05)

        self._simulate_key(Gdk.KEY_bracketright, Gdk.ModifierType.SHIFT_MASK)
        self.win.core.set_audio_delay.assert_called_with(0.05)

        self._simulate_key(Gdk.KEY_backslash, Gdk.ModifierType.SHIFT_MASK)
        self.win.core.set_audio_delay.assert_called_with(0.0)

    def test_TC_KEY_10_subtitle_sync_shortcuts(self):
        r"""TC-KEY-10: [/] adjusts subtitle sync ±0.5s, \ resets."""
        with patch.object(self.win.sub_mgr, "adjust_sync", return_value=-0.5) as mock_sync:
            self._simulate_key(Gdk.KEY_bracketleft)
            mock_sync.assert_called_with(-0.5)
            self.win.core.set_subtitle_delay.assert_called_with(-0.5)

        with patch.object(self.win.sub_mgr, "adjust_sync", return_value=0.5) as mock_sync:
            self._simulate_key(Gdk.KEY_bracketright)
            mock_sync.assert_called_with(0.5)
            self.win.core.set_subtitle_delay.assert_called_with(0.5)

        with patch.object(self.win.sub_mgr, "reset_sync") as mock_reset:
            self._simulate_key(Gdk.KEY_backslash)
            mock_reset.assert_called_once()
            self.win.core.set_subtitle_delay.assert_called_with(0.0)

    def test_TC_KEY_11_sub_position_and_font_size(self):
        """TC-KEY-11: Alt+Up/Down sub position, Alt+PgUp/PgDn sub font size."""
        # Subtitle position
        self._simulate_key(Gdk.KEY_Up, Gdk.ModifierType.MOD1_MASK)
        self.win.core.adjust_subtitle_pos.assert_called_with(-2)

        self._simulate_key(Gdk.KEY_Down, Gdk.ModifierType.MOD1_MASK)
        self.win.core.adjust_subtitle_pos.assert_called_with(+2)

        # Subtitle size
        init_sz = self.win.sub_mgr.font_size
        self._simulate_key(Gdk.KEY_Page_Up, Gdk.ModifierType.MOD1_MASK)
        self.win.core.set_subtitle_font_size.assert_called_with(init_sz + 2)

        self._simulate_key(Gdk.KEY_Page_Down, Gdk.ModifierType.MOD1_MASK)
        self.win.core.set_subtitle_font_size.assert_called_with(init_sz)

    def test_TC_KEY_12_track_cycling_shortcuts(self):
        """TC-KEY-12: A cycles audio, S cycles primary subtitle, Shift+S cycles secondary subtitle."""
        self._simulate_key(Gdk.KEY_a)
        self.win.core.cycle_audio_track.assert_called_once()

        self._simulate_key(Gdk.KEY_s)
        self.win.core.cycle_subtitle_track.assert_called_once()

        self._simulate_key(Gdk.KEY_s, Gdk.ModifierType.SHIFT_MASK)
        self.win.core.cycle_secondary_subtitle_track.assert_called_once()

    def test_TC_KEY_13_tab_tech_hud(self):
        """TC-KEY-13: Tab key toggles Technical Playback Information HUD."""
        init_state = self.win.osd.show_tech_info
        ret = self._simulate_key(Gdk.KEY_Tab)
        self.assertTrue(ret)
        self.assertEqual(self.win.osd.show_tech_info, not init_state)

    def test_TC_KEY_14_function_keys(self):
        """TC-KEY-14: F1 (About / Ctrl+F1 Media Info), F5/F6 (Control Box), F7 (Equalizer), F8/F12 (Playlist)."""
        with patch.object(self.win, "show_media_info_dialog") as mock_info:
            self._simulate_key(Gdk.KEY_F1, Gdk.ModifierType.CONTROL_MASK)
            mock_info.assert_called_once()

        with patch.object(self.win, "_show_about_dialog") as mock_about:
            self._simulate_key(Gdk.KEY_F1)
            mock_about.assert_called_once()

        with patch.object(self.win.control_box, "show_all") as mock_cbox:
            self._simulate_key(Gdk.KEY_F6)
            mock_cbox.assert_called()

        with patch.object(self.win.control_box, "select_tab") as mock_tab:
            self._simulate_key(Gdk.KEY_F7)
            mock_tab.assert_called_with(0)

        with patch.object(self.win.playlist_window, "show_all") as mock_pl:
            self._simulate_key(Gdk.KEY_F8)
            mock_pl.assert_called()
            self._simulate_key(Gdk.KEY_F12)
            self.assertEqual(mock_pl.call_count, 2)

    def test_TC_KEY_15_speed_shortcuts(self):
        """TC-KEY-15: Z (Normal 1.0x), X (Slower -0.1x), C (Faster +0.1x)."""
        self.win.core.speed = 1.0
        self._simulate_key(Gdk.KEY_c)
        self.win.core.set_speed.assert_called_with(1.1)

        self._simulate_key(Gdk.KEY_x)
        self.win.core.set_speed.assert_called_with(0.9)

        self._simulate_key(Gdk.KEY_z)
        self.win.core.set_speed.assert_called_with(1.0)

    def test_TC_KEY_16_procamp_color_shortcuts(self):
        """TC-KEY-16: Q (Reset), W/E (Brightness), R/T (Contrast), Y/U (Saturation), I/O (Hue)."""
        # Q: Reset
        self._simulate_key(Gdk.KEY_q)
        self.win.core.set_video_colors.assert_called_with(0, 0, 0, 0, 0)

        # W/E: Brightness
        self.win.shader_mgr.brightness = 0
        self._simulate_key(Gdk.KEY_e)
        self.assertEqual(self.win.shader_mgr.brightness, 1)
        self._simulate_key(Gdk.KEY_w)
        self.assertEqual(self.win.shader_mgr.brightness, 0)

        # R/T: Contrast
        self.win.shader_mgr.contrast = 0
        self._simulate_key(Gdk.KEY_t)
        self.assertEqual(self.win.shader_mgr.contrast, 1)
        self._simulate_key(Gdk.KEY_r)
        self.assertEqual(self.win.shader_mgr.contrast, 0)

        # Y/U: Saturation
        self.win.shader_mgr.saturation = 0
        self._simulate_key(Gdk.KEY_u)
        self.assertEqual(self.win.shader_mgr.saturation, 1)
        self._simulate_key(Gdk.KEY_y)
        self.assertEqual(self.win.shader_mgr.saturation, 0)

        # I/O: Hue
        self.win.shader_mgr.hue = 0
        self._simulate_key(Gdk.KEY_o)
        self.assertEqual(self.win.shader_mgr.hue, 1)
        self._simulate_key(Gdk.KEY_i)
        self.assertEqual(self.win.shader_mgr.hue, 0)

    def test_TC_KEY_17_bookmark_shortcuts(self):
        """TC-KEY-17: P (Add bookmark), H/J (Prev/Next bookmark)."""
        self.win.core.current_file = "/media/test.mp4"
        self.win.core.position = 120.0
        with patch.object(self.win.db, "add_bookmark") as mock_add:
            self._simulate_key(Gdk.KEY_p)
            mock_add.assert_called_with("/media/test.mp4", 120.0)

        with patch.object(self.win.db, "get_bookmarks", return_value=[{"timestamp": 60.0}, {"timestamp": 180.0}]):
            with patch.object(self.win.core, "seek_absolute") as mock_seek:
                # Prev bookmark
                self._simulate_key(Gdk.KEY_h)
                mock_seek.assert_called_with(60.0)

                # Next bookmark
                self._simulate_key(Gdk.KEY_j)
                mock_seek.assert_called_with(180.0)

    def test_TC_KEY_18_entry_focus_ignores_shortcuts(self):
        """TC-KEY-18: Shortcuts are bypassed when focus is on a text Entry."""
        mock_entry = Gtk.Entry()
        with patch.object(self.win, "get_focus", return_value=mock_entry):
            ret = self._simulate_key(Gdk.KEY_space)
            self.assertFalse(ret, "Key press should pass through to text entry")
            self.win.core.play_pause.assert_not_called()

    def test_TC_KEY_19_video_scaling_shortcuts(self):
        """TC-KEY-19: Video frame scaling on numpad (KP_8,2,6,4,5,9,1) and alternative (Shift+Alt+Arrows/0/=/-)."""
        # 1. Height Scaling
        with patch.object(self.win, "handle_command", wraps=self.win.handle_command) as mock_cmd:
            # KP_8
            ret = self._simulate_key(Gdk.KEY_KP_8)
            self.assertTrue(ret)
            mock_cmd.assert_called_with("CMD_VIDEO_SCALE_HEIGHT_UP")
            self.win.core.scale_video_height.assert_called_with(0.05)

            # Shift + Alt + Up
            ret = self._simulate_key(Gdk.KEY_Up, Gdk.ModifierType.SHIFT_MASK | Gdk.ModifierType.MOD1_MASK)
            self.assertTrue(ret)
            mock_cmd.assert_called_with("CMD_VIDEO_SCALE_HEIGHT_UP")

            # KP_2
            ret = self._simulate_key(Gdk.KEY_KP_2)
            self.assertTrue(ret)
            mock_cmd.assert_called_with("CMD_VIDEO_SCALE_HEIGHT_DOWN")
            self.win.core.scale_video_height.assert_called_with(-0.05)

            # Shift + Alt + Down
            ret = self._simulate_key(Gdk.KEY_Down, Gdk.ModifierType.SHIFT_MASK | Gdk.ModifierType.MOD1_MASK)
            self.assertTrue(ret)
            mock_cmd.assert_called_with("CMD_VIDEO_SCALE_HEIGHT_DOWN")

            # 2. Width Scaling
            # KP_6
            ret = self._simulate_key(Gdk.KEY_KP_6)
            self.assertTrue(ret)
            mock_cmd.assert_called_with("CMD_VIDEO_SCALE_WIDTH_UP")
            self.win.core.scale_video_width.assert_called_with(0.05)

            # Shift + Alt + Right
            ret = self._simulate_key(Gdk.KEY_Right, Gdk.ModifierType.SHIFT_MASK | Gdk.ModifierType.MOD1_MASK)
            self.assertTrue(ret)
            mock_cmd.assert_called_with("CMD_VIDEO_SCALE_WIDTH_UP")

            # KP_4
            ret = self._simulate_key(Gdk.KEY_KP_4)
            self.assertTrue(ret)
            mock_cmd.assert_called_with("CMD_VIDEO_SCALE_WIDTH_DOWN")
            self.win.core.scale_video_width.assert_called_with(-0.05)

            # Shift + Alt + Left
            ret = self._simulate_key(Gdk.KEY_Left, Gdk.ModifierType.SHIFT_MASK | Gdk.ModifierType.MOD1_MASK)
            self.assertTrue(ret)
            mock_cmd.assert_called_with("CMD_VIDEO_SCALE_WIDTH_DOWN")

            # 3. Reset Dimensions
            # KP_5
            ret = self._simulate_key(Gdk.KEY_KP_5)
            self.assertTrue(ret)
            mock_cmd.assert_called_with("CMD_VIDEO_SCALE_RESET")
            self.win.core.reset_video_dimensions.assert_called()

            # KP_Begin (numpad 5 with NumLock off)
            ret = self._simulate_key(Gdk.KEY_KP_Begin)
            self.assertTrue(ret)
            mock_cmd.assert_called_with("CMD_VIDEO_SCALE_RESET")

            # Shift + Alt + 0 / Shift + Alt + parenright
            ret = self._simulate_key(Gdk.KEY_0, Gdk.ModifierType.SHIFT_MASK | Gdk.ModifierType.MOD1_MASK)
            self.assertTrue(ret)
            mock_cmd.assert_called_with("CMD_VIDEO_SCALE_RESET")

            ret = self._simulate_key(Gdk.KEY_parenright, Gdk.ModifierType.SHIFT_MASK | Gdk.ModifierType.MOD1_MASK)
            self.assertTrue(ret)
            mock_cmd.assert_called_with("CMD_VIDEO_SCALE_RESET")

            # 4. Zoom Scaling
            # KP_9
            ret = self._simulate_key(Gdk.KEY_KP_9)
            self.assertTrue(ret)
            mock_cmd.assert_called_with("CMD_VIDEO_ZOOM_IN")
            self.win.core.zoom_video.assert_called_with(0.05)

            # Shift + Alt + = / Shift + Alt + plus
            ret = self._simulate_key(Gdk.KEY_equal, Gdk.ModifierType.SHIFT_MASK | Gdk.ModifierType.MOD1_MASK)
            self.assertTrue(ret)
            mock_cmd.assert_called_with("CMD_VIDEO_ZOOM_IN")

            ret = self._simulate_key(Gdk.KEY_plus, Gdk.ModifierType.SHIFT_MASK | Gdk.ModifierType.MOD1_MASK)
            self.assertTrue(ret)
            mock_cmd.assert_called_with("CMD_VIDEO_ZOOM_IN")

            # KP_1
            ret = self._simulate_key(Gdk.KEY_KP_1)
            self.assertTrue(ret)
            mock_cmd.assert_called_with("CMD_VIDEO_ZOOM_OUT")
            self.win.core.zoom_video.assert_called_with(-0.05)

            # Shift + Alt + - / Shift + Alt + underscore
            ret = self._simulate_key(Gdk.KEY_minus, Gdk.ModifierType.SHIFT_MASK | Gdk.ModifierType.MOD1_MASK)
            self.assertTrue(ret)
            mock_cmd.assert_called_with("CMD_VIDEO_ZOOM_OUT")

            ret = self._simulate_key(Gdk.KEY_underscore, Gdk.ModifierType.SHIFT_MASK | Gdk.ModifierType.MOD1_MASK)
            self.assertTrue(ret)
            mock_cmd.assert_called_with("CMD_VIDEO_ZOOM_OUT")

        # 5. Verify existing Alt + KP_* window-resizing shortcuts are preserved
        with patch.object(self.win, "resize") as mock_resize:
            ret = self._simulate_key(Gdk.KEY_KP_1, Gdk.ModifierType.MOD1_MASK)
            self.assertTrue(ret)
            mock_resize.assert_called_once()  # 50% window size

            mock_resize.reset_mock()
            ret = self._simulate_key(Gdk.KEY_KP_2, Gdk.ModifierType.MOD1_MASK)
            self.assertTrue(ret)
            mock_resize.assert_called_once()  # 100% window size

            mock_resize.reset_mock()
            ret = self._simulate_key(Gdk.KEY_KP_4, Gdk.ModifierType.MOD1_MASK)
            self.assertTrue(ret)
            mock_resize.assert_called_once()  # 200% window size

        # 6. Verify existing Ctrl + Alt + Left/Right 5-minute seeks are preserved
        self._simulate_key(Gdk.KEY_Left, Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.MOD1_MASK)
        self.win.core.seek_relative.assert_called_with(-300.0)
        self._simulate_key(Gdk.KEY_Right, Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.MOD1_MASK)
        self.win.core.seek_relative.assert_called_with(300.0)

        # 7. Text input immunity
        entry = Gtk.Entry()
        with patch.object(self.win, "get_focus", return_value=entry):
            event = MagicMock()
            event.keyval = Gdk.KEY_KP_8
            event.state = 0
            self.assertFalse(self.win._on_key_press(self.win, event))

        # 8. Fullscreen and windowed functionality
        self.win.is_fullscreen = True
        ret = self._simulate_key(Gdk.KEY_KP_8)
        self.assertTrue(ret)
        self.win.is_fullscreen = False
        ret = self._simulate_key(Gdk.KEY_KP_8)
        self.assertTrue(ret)


class TestWindowLifecycleAndInteraction(unittest.TestCase):
    """Phase 2.C: Window Lifecycle, Fullscreen Transition & Cursor Auto-Hide."""

    def setUp(self):
        self.win = JonakiMainWindow()

    def tearDown(self):
        self.win.destroy()

    def test_TC_WIN_01_window_state_fullscreen_event(self):
        """TC-WIN-01: Gdk.WindowState.FULLSCREEN event handling."""
        event = MagicMock()
        event.new_window_state = Gdk.WindowState.FULLSCREEN
        self.win._on_window_state_event(self.win, event)
        self.assertTrue(self.win.is_fullscreen)

        # Unfullscreen
        event.new_window_state = 0
        self.win._on_window_state_event(self.win, event)
        self.assertFalse(self.win.is_fullscreen)
        self.assertTrue(self.win._controls_visible)
        self.assertTrue(self.win._cursor_visible)

    def test_TC_WIN_02_cursor_auto_hide_during_playback(self):
        """TC-WIN-02: Cursor hides after 2.5s of inactivity during playback."""
        self.win.core.state = PlaybackState.PLAYING
        self.win._last_mouse_move_time = time.time() - 3.0  # 3s inactive
        self.win._cursor_visible = True

        self.win._on_ui_tick()
        self.assertFalse(self.win._cursor_visible, "Cursor must auto-hide after 2.5s during playback")

        # Mouse motion restores cursor
        motion_event = MagicMock()
        motion_event.x = 100
        motion_event.y = 100
        self.win._on_mouse_motion(self.win.video_area, motion_event)
        self.assertTrue(self.win._cursor_visible, "Cursor must restore immediately on motion")

    def test_TC_WIN_03_fullscreen_control_bar_auto_hide(self):
        """TC-WIN-03: Bottom skin control bar hides in fullscreen during playback."""
        self.win.is_fullscreen = True
        self.win.core.state = PlaybackState.PLAYING
        self.win._controls_visible = True
        self.win._last_mouse_move_time = time.time() - 3.0

        self.win._on_ui_tick()
        self.assertFalse(self.win._controls_visible, "Control bar must hide in fullscreen")
        self.assertFalse(self.win.skin_area.get_visible())

        # Mouse motion restores controls
        motion_event = MagicMock()
        motion_event.x = 200
        motion_event.y = 200
        self.win._on_mouse_motion(self.win.video_area, motion_event)
        self.assertTrue(self.win._controls_visible, "Controls must restore on motion")
        self.assertTrue(self.win.skin_area.get_visible())

    def test_TC_WIN_04_controls_persistent_when_paused_or_idle(self):
        """TC-WIN-04: Controls and cursor remain visible when paused, stopped, or idle."""
        for state in (PlaybackState.PAUSED, PlaybackState.STOPPED, PlaybackState.IDLE):
            self.win.core.state = state
            self.win._cursor_visible = False
            self.win._controls_visible = False
            self.win._last_mouse_move_time = time.time() - 10.0

            self.win._on_ui_tick()
            self.assertTrue(self.win._cursor_visible, f"Cursor must stay visible in {state}")
            self.assertTrue(self.win._controls_visible, f"Controls must stay visible in {state}")

    def test_TC_WIN_05_stay_on_top_toggle(self):
        """TC-WIN-05: Ctrl+T toggles stay-on-top (keep_above)."""
        with patch.object(self.win, "set_keep_above") as mock_keep:
            event = MagicMock()
            event.keyval = Gdk.KEY_t
            event.state = Gdk.ModifierType.CONTROL_MASK
            self.win._on_key_press(self.win, event)
            self.assertTrue(self.win._is_keep_above)
            mock_keep.assert_called_with(True)

            # Toggle off
            self.win._on_key_press(self.win, event)
            self.assertFalse(self.win._is_keep_above)
            mock_keep.assert_called_with(False)

    def test_TC_WIN_06_video_scroll_volume(self):
        """TC-WIN-06: Scroll wheel over video adjusts volume."""
        with patch.object(self.win.core, "adjust_volume") as mock_vol:
            event_up = MagicMock()
            event_up.direction = Gdk.ScrollDirection.UP
            self.win._on_video_scroll(self.win.video_area, event_up)
            mock_vol.assert_called_with(+2.0)

            event_down = MagicMock()
            event_down.direction = Gdk.ScrollDirection.DOWN
            self.win._on_video_scroll(self.win.video_area, event_down)
            mock_vol.assert_called_with(-2.0)


class TestPlaylistAndNavigation(unittest.TestCase):
    """Phase 2.D: Playlist, Search Filter, Sort, Shuffle & Media Navigation."""

    def setUp(self):
        self.win = JonakiMainWindow()
        self.win.core.wid = 12345  # Simulated realized window
        self.pl_win = self.win.playlist_window

    def tearDown(self):
        self.win.destroy()

    def test_TC_PL_01_add_files_and_clear_existing(self):
        """TC-PL-01: Adding files to playlist and clear_existing flag."""
        files1 = ["/media/video1.mkv", "/media/video2.mp4"]
        self.win.add_files_to_playlist(files1, auto_play=False, clear_existing=True)
        self.assertEqual(len(self.win.playlist), 2)
        self.assertEqual(self.win.playlist[0]["path"], "/media/video1.mkv")

        # Append more files without clearing
        files2 = ["/media/audio1.mp3"]
        self.win.add_files_to_playlist(files2, auto_play=False, clear_existing=False)
        self.assertEqual(len(self.win.playlist), 3)

    def test_TC_PL_02_duplicate_handling(self):
        """TC-PL-02: Adding duplicate files appends them distinctly."""
        files = ["/media/video1.mkv", "/media/video1.mkv"]
        self.win.add_files_to_playlist(files, auto_play=False, clear_existing=True)
        self.assertEqual(len(self.win.playlist), 2)
        self.assertEqual(len(self.pl_win.list_store), 2)

    def test_TC_PL_03_remove_from_playlist_boundaries(self):
        """TC-PL-03: Removing files from playlist at beginning, middle, and end."""
        files = ["/media/1.mp4", "/media/2.mp4", "/media/3.mp4"]
        self.win.add_files_to_playlist(files, clear_existing=True)
        self.win.current_index = 1  # Playing item 2

        # Remove item 0 (before current)
        self.win.remove_from_playlist(0)
        self.assertEqual(len(self.win.playlist), 2)
        self.assertEqual(self.win.current_index, 0, "Current index should decrement when earlier item is removed")

        # Remove currently playing item
        with patch.object(self.win, "play_index") as mock_play:
            self.win.remove_from_playlist(0)
            self.assertEqual(len(self.win.playlist), 1)
            mock_play.assert_called_with(0)

        # Remove last remaining item
        with patch.object(self.win.core, "stop") as mock_stop:
            self.win.remove_from_playlist(0)
            self.assertEqual(len(self.win.playlist), 0)
            self.assertEqual(self.win.current_index, -1)
            mock_stop.assert_called_once()

    def test_TC_PL_04_sort_playlist(self):
        """TC-PL-04: Sorting playlist alphabetically preserves current track index."""
        files = ["/media/Zebra.mp4", "/media/Alpha.mp4", "/media/Beta.mp4"]
        self.win.add_files_to_playlist(files, clear_existing=True)
        self.win.current_index = 0  # Playing Zebra

        self.win.sort_playlist()
        titles = [x["title"] for x in self.win.playlist]
        self.assertEqual(titles, ["Alpha.mp4", "Beta.mp4", "Zebra.mp4"])
        # Zebra is now at index 2
        self.assertEqual(self.win.current_index, 2, "Current index must follow sorted track")

    def test_TC_PL_05_shuffle_playlist(self):
        """TC-PL-05: Shuffling playlist maintains all items and updates current index."""
        files = [f"/media/{i}.mp4" for i in range(10)]
        self.win.add_files_to_playlist(files, clear_existing=True)
        self.win.current_index = 5
        cur_file = self.win.playlist[5]["path"]

        self.win.shuffle_playlist()
        self.assertEqual(len(self.win.playlist), 10)
        # Track where cur_file ended up
        self.assertEqual(self.win.playlist[self.win.current_index]["path"], cur_file)

    def test_TC_PL_06_next_prev_boundaries(self):
        """TC-PL-06: Next/Previous playlist navigation wraps correctly around boundaries."""
        files = ["/media/1.mp4", "/media/2.mp4", "/media/3.mp4"]
        self.win.add_files_to_playlist(files, clear_existing=True)

        with patch.object(self.win, "play_index") as mock_play:
            # At index 0, prev wraps to last
            self.win.current_index = 0
            self.win.play_prev()
            mock_play.assert_called_with(2)

            # At index 2, next wraps to 0
            self.win.current_index = 2
            self.win.play_next()
            mock_play.assert_called_with(0)

    def test_TC_PL_07_empty_playlist_navigation(self):
        """TC-PL-07: Calling play_next/play_prev on empty playlist does not raise exception."""
        self.win.playlist.clear()
        self.win.current_index = -1
        try:
            self.win.play_next()
            self.win.play_prev()
        except Exception as e:
            self.fail(f"Navigation on empty playlist raised exception: {e}")

    def test_TC_PL_08_search_filter_edge_cases(self):
        """TC-PL-08: Playlist search filtering with special characters, case insensitivity."""
        items = [
            {"path": "/media/[Fansub] Anime - 01 (1080p).mkv", "title": "[Fansub] Anime - 01 (1080p)", "duration": 1420.0},
            {"path": "/media/Documentary.mp4", "title": "Documentary", "duration": 3600.0},
            {"path": "/media/Music Video.webm", "title": "Music Video", "duration": 210.0}
        ]
        self.win.playlist = items
        self.pl_win.update_playlist(items)

        # 1. Special regex characters '['
        self.pl_win.search_entry.set_text("[fansub]")
        self.pl_win._on_search_changed(self.pl_win.search_entry)
        self.assertEqual(len(self.pl_win.list_store), 1)
        self.assertEqual(self.pl_win.list_store[0][0], 1)

        # 2. Case insensitive query
        self.pl_win.search_entry.set_text("mUsIc")
        self.pl_win._on_search_changed(self.pl_win.search_entry)
        self.assertEqual(len(self.pl_win.list_store), 1)
        self.assertEqual(self.pl_win.list_store[0][0], 3)

        # 3. Empty query resets to full list
        self.pl_win.search_entry.set_text("")
        self.pl_win._on_search_changed(self.pl_win.search_entry)
        self.assertEqual(len(self.pl_win.list_store), 3)

        # 4. Non-matching query
        self.pl_win.search_entry.set_text("NonExistentXYZ")
        self.pl_win._on_search_changed(self.pl_win.search_entry)
        self.assertEqual(len(self.pl_win.list_store), 0)

    def test_TC_PL_09_remove_when_nothing_selected(self):
        """TC-PL-09: Clicking remove with no treeview row selected does not crash."""
        self.pl_win.tree_view.get_selection().unselect_all()
        try:
            self.pl_win._on_remove_clicked(None)
        except Exception as e:
            self.fail(f"_on_remove_clicked without selection crashed: {e}")


class TestSecondaryDialogsAndContextMenus(unittest.TestCase):
    """Phase 2.C & 2.D: Control Box, Media Info Dialog, Context Menu Subsystems."""

    def setUp(self):
        self.win = JonakiMainWindow()
        self.cbox = self.win.control_box
        self.cbox.show_all()

    def tearDown(self):
        self.win.destroy()

    def test_TC_CBOX_01_all_5_tabs_present(self):
        """TC-CBOX-01: Verify Control Box contains 5 functional tabs."""
        self.assertEqual(self.cbox.notebook.get_n_pages(), 5)
        expected_labels = ["Audio", "Video", "Subtitles", "Playback", "Shaders"]
        for i, lbl in enumerate(expected_labels):
            tab_label = self.cbox.notebook.get_tab_label_text(self.cbox.notebook.get_nth_page(i))
            self.assertEqual(tab_label, lbl)

    def test_TC_CBOX_02_sync_controls_without_feedback_loop(self):
        """TC-CBOX-02: ControlBox update_controls avoids signal feedback loops."""
        self.win.shader_mgr.brightness = 25
        self.win.shader_mgr.contrast = -15
        self.win.core.speed = 1.75
        self.win.sub_mgr.font_size = 32

        # Trigger update
        self.cbox.update_controls()
        self.assertEqual(self.cbox.bright_scale.get_value(), 25)
        self.assertEqual(self.cbox.contrast_scale.get_value(), -15)
        self.assertEqual(self.cbox.speed_scale.get_value(), 1.75)
        self.assertEqual(self.cbox.size_scale.get_value(), 32)
        self.assertFalse(self.cbox._updating_controls, "_updating_controls flag must be reset to False")

    def test_TC_CBOX_03_denoise_shader_in_control_box(self):
        """TC-CBOX-03: Verify DEF-UI-02 fix: denoise.hook is present in Control Box shaders tab."""
        has_denoise = "denoise.hook" in self.cbox.shader_checks
        self.assertTrue(has_denoise, "DEF-UI-02 verified: denoise.hook is now present in Control Box shaders tab")

    def test_TC_INFO_01_media_info_dialog_full_metrics(self):
        """TC-INFO-01: MediaInfoDialog renders complete audio/video metrics."""
        dialog = self.win.media_info_dialog
        info = {
            "path": "/media/4k_hdr_movie.mkv",
            "filesize_bytes": 4500000000,
            "duration_sec": 7254.12,
            "width": 3840,
            "height": 2160,
            "fps": 23.976,
            "video_codec": "HEVC",
            "pixel_format": "yuv420p10le",
            "colormatrix": "bt2020nc",
            "video_bitrate": 18500000,
            "audio_codec": "TrueHD Atmos",
            "audio_channels": 8,
            "sample_rate": 48000,
            "audio_bitrate": 4500000,
            "hwdec": "nvdec",
            "audio_delay": 0.05,
            "sub_delay": -0.5,
            "tracks": [
                {"id": 1, "type": "video", "codec": "hevc"},
                {"id": 2, "type": "audio", "codec": "truehd", "lang": "eng"},
                {"id": 3, "type": "sub", "codec": "subrip", "lang": "eng", "selected": True}
            ]
        }
        dialog.update_info(info)
        report = dialog.current_report_text
        self.assertIn("HEVC", report)
        self.assertIn("3840 x 2160", report)
        self.assertIn("TrueHD Atmos", report)
        self.assertIn("Hardware Acceleration Active (NVDEC)", report)
        self.assertIn("Track #3: [eng] subrip [ACTIVE]", report)

    def test_TC_INFO_02_media_info_dialog_empty_info(self):
        """TC-INFO-02: MediaInfoDialog handles empty dictionary without crashing."""
        dialog = self.win.media_info_dialog
        try:
            dialog.update_info({})
        except Exception as e:
            self.fail(f"update_info with empty dict failed: {e}")
        self.assertIn("No file loaded", dialog.current_report_text)

    def test_TC_INFO_03_media_info_clipboard_copy(self):
        """TC-INFO-03: MediaInfoDialog copy button places text into clipboard."""
        dialog = self.win.media_info_dialog
        dialog.update_info({"path": "/media/test.mp4"})
        dialog._on_copy_clicked(None)
        clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        self.assertEqual(clipboard.wait_for_text(), dialog.current_report_text)
        self.assertIn("Copied to clipboard", dialog.status_label.get_text())

    def test_TC_CTX_01_context_menu_stream_selection(self):
        """TC-CTX-01: Context menu dynamic audio and subtitle stream lists."""
        menu = self.win.context_menu
        mock_core = MagicMock()
        mock_core.get_audio_tracks.return_value = [
            {"id": 1, "lang": "eng", "title": "English 5.1", "audio-channels": 6, "selected": True},
            {"id": 2, "lang": "jpn", "title": "Japanese 2.0", "audio-channels": 2, "selected": False}
        ]
        mock_core.get_current_audio_track_id.return_value = 1

        mock_core.get_subtitle_tracks.return_value = [
            {"id": 1, "lang": "eng", "title": "Full Subtitles", "selected": True},
            {"id": 2, "lang": "spa", "title": "Spanish Subtitles", "selected": False}
        ]
        mock_core.get_current_subtitle_track_id.return_value = 1
        mock_core.get_current_secondary_subtitle_track_id.return_value = "no"

        menu.refresh_dynamic_menus(mock_core)

        # Audio stream items
        a_items = [it.get_label() for it in menu.audio_streams_menu.get_children() if isinstance(it, Gtk.MenuItem) and it.get_label()]
        self.assertTrue(any("✓ Track #1" in label for label in a_items))
        self.assertTrue(any("Track #2" in label for label in a_items))

        # Subtitle stream items
        s_items = [it.get_label() for it in menu.sub_streams_menu.get_children() if isinstance(it, Gtk.MenuItem) and it.get_label()]
        self.assertTrue(any("✓ Track #1" in label for label in s_items))

        # Secondary subtitle stream items (Dual subtitles)
        sec_items = [it.get_label() for it in menu.sub_sec_streams_menu.get_children() if isinstance(it, Gtk.MenuItem) and it.get_label()]
        self.assertTrue(any("✓ Disable Secondary Subtitle" in label for label in sec_items))
        self.assertTrue(any("Track #1" in label for label in sec_items))

    def test_TC_CTX_02_aspect_ratio_and_orientation_menus(self):
        """TC-CTX-02: Aspect ratio and video orientation submenus."""
        menu = self.win.context_menu
        aspect_labels = [it.get_label() for it in menu.aspect_menu.get_children() if isinstance(it, Gtk.MenuItem) and it.get_label()]
        self.assertTrue(any("16:9" in l for l in aspect_labels))
        self.assertTrue(any("4:3" in l for l in aspect_labels))
        self.assertTrue(any("Stretch to Window" in l for l in aspect_labels))

        orient_labels = [it.get_label() for it in menu.orientation_menu.get_children() if isinstance(it, Gtk.MenuItem) and it.get_label()]
        self.assertTrue(any("Rotate 90°" in l for l in orient_labels))
        self.assertTrue(any("Horizontal Flip" in l for l in orient_labels))
        self.assertTrue(any("Vertical Flip" in l for l in orient_labels))

    def test_TC_CTX_03_context_menu_freshly_started(self):
        """TC-CTX-03: Context menu opens when right-clicked on freshly started player."""
        win = self.win
        win.show_all()
        while Gtk.events_pending():
            Gtk.main_iteration_do(False)

        # Confirm player is freshly started (IDLE, no current file)
        self.assertEqual(win.core.state, PlaybackState.IDLE)
        self.assertIsNone(win.core.current_file)

        # 1. Right-click on video_area
        win.context_menu.menu.popdown()
        while Gtk.events_pending():
            Gtk.main_iteration_do(False)
        ev_video = Gdk.EventButton()
        ev_video.type = Gdk.EventType.BUTTON_PRESS
        ev_video.button = 3
        ev_video.time = 0
        ev_video.x = 200.0
        ev_video.y = 200.0
        handled = win._on_video_button_press(win.video_area, ev_video)
        self.assertTrue(handled)
        self.assertTrue(win.context_menu.menu.get_visible())

        # 2. Right-click on osd_layer (the overlay visible on fresh start)
        win.context_menu.menu.popdown()
        while Gtk.events_pending():
            Gtk.main_iteration_do(False)
        ev_osd = Gdk.EventButton()
        ev_osd.type = Gdk.EventType.BUTTON_PRESS
        ev_osd.button = 3
        ev_osd.time = 0
        ev_osd.x = 200.0
        ev_osd.y = 200.0
        handled_osd = win._on_video_button_press(win.osd_layer, ev_osd)
        self.assertTrue(handled_osd)
        self.assertTrue(win.context_menu.menu.get_visible())

        # 3. Right-click on bottom skin_area
        win.context_menu.menu.popdown()
        while Gtk.events_pending():
            Gtk.main_iteration_do(False)
        ev_skin = Gdk.EventButton()
        ev_skin.type = Gdk.EventType.BUTTON_PRESS
        ev_skin.button = 3
        ev_skin.time = 0
        ev_skin.x = 200.0
        ev_skin.y = 10.0
        handled_skin = win._on_skin_button_press(win.skin_area, ev_skin)
        self.assertTrue(handled_skin)
        self.assertTrue(win.context_menu.menu.get_visible())

        # 4. Right-click on toplevel window
        win.context_menu.menu.popdown()
        while Gtk.events_pending():
            Gtk.main_iteration_do(False)
        ev_win = Gdk.EventButton()
        ev_win.type = Gdk.EventType.BUTTON_PRESS
        ev_win.button = 3
        ev_win.time = 0
        ev_win.x = 10.0
        ev_win.y = 10.0
        handled_win = win._on_window_button_press(win, ev_win)
        self.assertTrue(handled_win)
        self.assertTrue(win.context_menu.menu.get_visible())

    def test_TC_OSD_01_osd_notifications_and_hud(self):
        """TC-OSD-01: OSD notifications and Technical HUD rendering."""
        osd = OSDOverlay()
        osd.show_osd("Test OSD Message", 1.0)
        self.assertEqual(osd.message, "Test OSD Message")
        self.assertGreater(osd.message_expire_time, time.time())

        # Render without crashing
        surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, 800, 600)
        cr = cairo.Context(surf)
        info = {
            "file_path": "/media/test.mp4",
            "fps": 60.0,
            "hwdec": "vaapi",
            "video_codec": "AV1",
            "audio_codec": "OPUS",
            "width": 1920,
            "height": 1080
        }
        osd.show_tech_info = True
        try:
            osd.render(cr, 800, 600, info, 10.0, 100.0)
        except Exception as e:
            self.fail(f"OSD render failed: {e}")


if __name__ == "__main__":
    unittest.main()
