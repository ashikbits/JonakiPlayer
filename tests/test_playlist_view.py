"""
Unit tests for PlaylistWindow UI component (duration formatting, search filtering, index mapping).
"""

import unittest
import os
import sys
from unittest.mock import MagicMock
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from ui.playlist_view import PlaylistWindow


class TestPlaylistView(unittest.TestCase):
    def setUp(self):
        self.mock_player = MagicMock()
        self.mock_player.playlist = [
            {"title": "Track 1", "duration": 45.0, "path": "/media/track1.mp3"},
            {"title": "Track 2", "duration": 125.0, "path": "/media/track2.mp3"},
            {"title": "Movie Feature", "duration": 7325.0, "path": "/media/movie.mkv"},
        ]
        self.win = PlaylistWindow(self.mock_player)

    def tearDown(self):
        self.win.destroy()

    def test_format_duration(self):
        # BUG-024: Verify durations with hours include h:mm:ss
        self.assertEqual(self.win._format_duration(0.0), "00:00")
        self.assertEqual(self.win._format_duration(45.0), "00:45")
        self.assertEqual(self.win._format_duration(125.0), "02:05")
        self.assertEqual(self.win._format_duration(3600.0), "1:00:00")
        self.assertEqual(self.win._format_duration(7325.0), "2:02:05")

    def test_update_playlist(self):
        self.win.update_playlist(self.mock_player.playlist)
        self.assertEqual(len(self.win.list_store), 3)

        # Check rows
        self.assertEqual(self.win.list_store[0][0], 1)
        self.assertEqual(self.win.list_store[0][1], "Track 1")
        self.assertEqual(self.win.list_store[0][2], "00:45")

        self.assertEqual(self.win.list_store[2][0], 3)
        self.assertEqual(self.win.list_store[2][1], "Movie Feature")
        self.assertEqual(self.win.list_store[2][2], "2:02:05")

        # Summary check
        self.assertIn("3 items", self.win.lbl_summary.get_text())
        self.assertIn("2:04:55", self.win.lbl_summary.get_text())

    def test_search_filtering_preserves_indices(self):
        # BUG-014 & BUG-044: Search filtering preserves original 1-based index in playlist
        self.win.update_playlist(self.mock_player.playlist)

        self.win.search_entry.set_text("movie")
        self.win._on_search_changed(self.win.search_entry)

        self.assertEqual(len(self.win.list_store), 1)
        # Should retain original index 3 (not 1)
        self.assertEqual(self.win.list_store[0][0], 3)
        self.assertEqual(self.win.list_store[0][1], "Movie Feature")

        # Activating row activates original index 2 (3 - 1)
        path = Gtk.TreePath.new_first()
        self.win._on_row_activated(self.win.tree_view, path, None)
        self.mock_player.play_index.assert_called_with(2)

    def test_search_filter_remove(self):
        # Removing an item while filtered should remove the item at its original index
        self.win.update_playlist(self.mock_player.playlist)

        self.win.search_entry.set_text("track 2")
        self.win._on_search_changed(self.win.search_entry)

        self.assertEqual(len(self.win.list_store), 1)
        self.assertEqual(self.win.list_store[0][0], 2)

        # Select row
        path = Gtk.TreePath.new_first()
        self.win.tree_view.get_selection().select_path(path)

        self.win._on_remove_clicked(None)
        self.mock_player.remove_from_playlist.assert_called_with(1)  # Index 2 - 1 = 1


if __name__ == "__main__":
    unittest.main()
