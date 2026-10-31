"""
Unit tests for mouse cursor visibility and control auto-hide behavior.
"""

import unittest
import sys
import os
import time
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk
from ui.main_window import JonakiMainWindow
from core.engine import PlaybackState


class TestCursorAndControls(unittest.TestCase):
    def setUp(self):
        self.win = JonakiMainWindow()

    def tearDown(self):
        self.win.destroy()

    def test_cursor_visibility_initial_state(self):
        self.assertTrue(self.win._cursor_visible)
        self.assertTrue(self.win._controls_visible)

    def test_mouse_motion_restores_cursor_and_controls(self):
        # BUG 8.3: Mock GDK windows to verify real set_cursor operations
        mock_gdk_win = MagicMock()
        with unittest.mock.patch.object(self.win, "get_window", return_value=mock_gdk_win), \
             unittest.mock.patch.object(self.win.video_area, "get_window", return_value=mock_gdk_win), \
             unittest.mock.patch.object(self.win.osd_layer, "get_window", return_value=mock_gdk_win):

            # Simulate hidden cursor and controls
            self.win._set_cursor_visible(False)
            self.win._controls_visible = False
            self.assertFalse(self.win._cursor_visible)
            self.assertFalse(self.win._controls_visible)
            # Verify blank cursor was set on GDK windows
            mock_gdk_win.set_cursor.assert_called()

            # Simulate mouse motion event
            mock_event = MagicMock()
            mock_event.x = 150
            mock_event.y = 200
            mock_event.x_root = 150
            mock_event.y_root = 200

            mock_gdk_win.reset_mock()
            self.win._on_mouse_motion(self.win.video_area, mock_event)

            # Both cursor and controls must be restored immediately
            self.assertTrue(self.win._cursor_visible)
            self.assertTrue(self.win._controls_visible)
            # Verify visible cursor (None = default pointer) was set
            mock_gdk_win.set_cursor.assert_called_with(None)

    def test_auto_hide_cursor_during_playback(self):
        self.win.core.state = PlaybackState.PLAYING
        self.win._last_mouse_move_time = time.time() - 3.0  # Inactive for 3 seconds
        self.win._cursor_visible = True

        self.win._on_ui_tick()

        # Cursor should be hidden after 2.5s of inactivity during playback
        self.assertFalse(self.win._cursor_visible)

        # Move mouse
        mock_event = MagicMock()
        mock_event.x = 250
        mock_event.y = 300
        mock_event.x_root = 250
        mock_event.y_root = 300

        self.win._on_mouse_motion(self.win.video_area, mock_event)
        self.assertTrue(self.win._cursor_visible)

    def test_fullscreen_controls_auto_hide(self):
        # BUG 8.2: Test control bar auto-hiding in fullscreen during playback
        self.win.is_fullscreen = True
        self.win.core.state = PlaybackState.PLAYING
        self.win._controls_visible = True
        self.win.skin_area.show()
        self.win._last_mouse_move_time = time.time() - 3.0

        self.win._on_ui_tick()

        # In fullscreen after 2.5s inactivity, controls must be hidden
        self.assertFalse(self.win._controls_visible)
        self.assertFalse(self.win.skin_area.get_visible())
        self.assertFalse(self.win.top_bar.get_visible())

        # Mouse motion should restore control bar and top bar visibility
        mock_event = MagicMock()
        mock_event.x = 250
        mock_event.y = 300
        mock_event.x_root = 250
        mock_event.y_root = 300

        self.win._on_mouse_motion(self.win.video_area, mock_event)
        self.assertTrue(self.win._controls_visible)
        self.assertTrue(self.win.skin_area.get_visible())
        self.assertTrue(self.win.top_bar.get_visible())

    def test_fullscreen_overlay_does_not_resize_video(self):
        # In fullscreen, show/hide of skin_area and top_bar should not resize video_area
        self.win.set_default_size(1000, 700)
        self.win.show_all()
        self.win.is_fullscreen = True
        self.win.skin_area.show()
        self.win.top_bar.show()

        while Gtk.events_pending():
            Gtk.main_iteration()

        w_shown = self.win.video_area.get_allocation().width
        h_shown = self.win.video_area.get_allocation().height

        # Hide both bars as in auto-hide
        self.win.skin_area.hide()
        self.win.top_bar.hide()

        while Gtk.events_pending():
            Gtk.main_iteration()

        w_hidden = self.win.video_area.get_allocation().width
        h_hidden = self.win.video_area.get_allocation().height

        # Video dimensions should be completely identical (no layout resize)
        self.assertEqual(w_shown, w_hidden)
        self.assertEqual(h_shown, h_hidden)

    def test_cursor_remains_visible_when_not_playing(self):
        self.win.core.state = PlaybackState.PAUSED
        self.win._last_mouse_move_time = time.time() - 5.0
        self.win._cursor_visible = False

        self.win._on_ui_tick()

        # When paused, cursor must be made visible
        self.assertTrue(self.win._cursor_visible)
        self.assertTrue(self.win._controls_visible)


if __name__ == "__main__":
    unittest.main()
