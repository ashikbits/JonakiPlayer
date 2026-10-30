"""
Unit tests for MediaDatabase persistence layer.
"""

import unittest
import os
import shutil
import tempfile
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from core.media_db import MediaDatabase


class TestMediaDatabase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test_mediadb.sqlite")
        self.db = MediaDatabase(self.db_path)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_playback_resume(self):
        file_path = "/home/user/video.mp4"
        self.db.save_playback_position(file_path, position=124.5, duration=3600.0)
        pos = self.db.get_playback_position(file_path)
        self.assertEqual(pos, 124.5)

        # BUG 5.3: Finished playback (position >= 95% of duration) resets resume position to 0.0
        finished_file = "/home/user/completed_video.mp4"
        self.db.save_playback_position(finished_file, position=3500.0, duration=3600.0)
        finished_pos = self.db.get_playback_position(finished_file)
        self.assertEqual(finished_pos, 0.0)

        # Re-opening completed video (position=0.0) must not corrupt completion state or reset position to 3500.0
        self.db.save_playback_position(finished_file, position=0.0, duration=3600.0)
        reopened_pos = self.db.get_playback_position(finished_file)
        self.assertEqual(reopened_pos, 0.0)

        # Playing past 5 seconds updates resume position properly
        self.db.save_playback_position(finished_file, position=25.0, duration=3600.0)
        self.assertEqual(self.db.get_playback_position(finished_file), 25.0)

        # Explicit reset resets position to 0.0
        self.db.reset_playback_position(finished_file)
        self.assertEqual(self.db.get_playback_position(finished_file), 0.0)

    def test_bookmarks(self):
        file_path = "/home/user/movie.mkv"
        bm_id = self.db.add_bookmark(file_path, timestamp=65.0, title="Intro Scene")
        self.assertIsNotNone(bm_id)
        bms = self.db.get_bookmarks(file_path)
        self.assertEqual(len(bms), 1)
        self.assertEqual(bms[0]["timestamp"], 65.0)
        self.assertEqual(bms[0]["title"], "Intro Scene")

        self.db.delete_bookmark(bm_id)
        self.assertEqual(len(self.db.get_bookmarks(file_path)), 0)

    def test_settings(self):
        self.db.set_setting("skin", "Default.dsf")
        self.assertEqual(self.db.get_setting("skin"), "Default.dsf")
        self.assertIsNone(self.db.get_setting("non_existent"))

    def test_add_to_history(self):
        file_path = "/home/user/series.mkv"
        self.db.add_to_history(file_path, title="Episode 1", duration=2400.0, position=500.0)
        recent = self.db.get_recent_history(5)
        self.assertTrue(any(r["file_path"] == file_path for r in recent))
        entry = next(r for r in recent if r["file_path"] == file_path)
        self.assertEqual(entry["title"], "Episode 1")
        self.assertEqual(entry["last_position"], 500.0)

    def test_add_to_history_preserves_resume_position(self):
        # BUG 3.1: Re-opening file (position=0.0) must not overwrite existing saved resume position
        file_path = "/home/user/movie.mp4"
        self.db.save_playback_position(file_path, position=350.0, duration=1200.0)
        self.assertEqual(self.db.get_playback_position(file_path), 350.0)

        # Call add_to_history with default/0.0 position upon re-opening
        self.db.add_to_history(file_path, title="Movie", duration=1200.0, position=0.0)
        self.assertEqual(self.db.get_playback_position(file_path), 350.0)

    def test_save_playlist_with_file_path_key(self):
        # BUG 3.2: Items containing "file_path" key must not have paths overwritten with empty strings
        album_id = self.db.add_album("Favorites")
        items = [
            {"file_path": "/media/song.mp3", "title": "Song", "duration": 180.0}
        ]
        self.db.save_playlist(items, album_id=album_id)
        saved = self.db.get_playlist_items(album_id=album_id)
        self.assertEqual(len(saved), 1)
        self.assertEqual(saved[0]["file_path"], "/media/song.mp3")

    def test_foreign_key_cascading_delete(self):
        # BUG 3.3: Foreign keys enabled ensures deleting an album cascades to its items
        album_id = self.db.add_album("Temporary Album")
        items = [{"path": "/media/track.flac", "title": "Track", "duration": 200.0}]
        self.db.save_playlist(items, album_id=album_id)
        self.assertEqual(len(self.db.get_playlist_items(album_id)), 1)

        with self.db._get_connection() as conn:
            conn.execute("DELETE FROM playlist_albums WHERE id = ?", (album_id,))
            conn.commit()

        self.assertEqual(len(self.db.get_playlist_items(album_id)), 0)

    def test_duration_null_handling(self):
        # BUG 3.4: NULL duration in database row does not cause max(duration, ?) to evaluate to NULL
        file_path = "/media/corrupt_dur.mkv"
        with self.db._get_connection() as conn:
            conn.execute("INSERT INTO playback_history (file_path, last_position, last_played_at, duration) VALUES (?, ?, ?, NULL)",
                         (file_path, 10.0, 1000.0))
            conn.commit()

        self.db.save_playback_position(file_path, position=20.0, duration=150.0)
        with self.db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT duration FROM playback_history WHERE file_path = ?", (file_path,))
            dur = cursor.fetchone()["duration"]
            self.assertEqual(dur, 150.0)


if __name__ == "__main__":
    unittest.main()
