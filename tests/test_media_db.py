"""
Unit tests for MediaDatabase persistence layer.
"""

import unittest
import os
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
        if os.path.exists(self.db_path):
            os.unlink(self.db_path)
        os.rmdir(self.temp_dir)

    def test_playback_resume(self):
        file_path = "/home/user/video.mp4"
        self.db.save_playback_position(file_path, position=124.5, duration=3600.0)
        pos = self.db.get_playback_position(file_path)
        self.assertEqual(pos, 124.5)

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


if __name__ == "__main__":
    unittest.main()
