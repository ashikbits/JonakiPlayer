"""
Unit tests for Jonaki CLI argument parsing.
Verifies switch parsing and options handling.
"""

import unittest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from jonaki import parse_arguments, parse_seek_time


class TestJonakiCLI(unittest.TestCase):
    def test_parse_seek_time(self):
        # Seconds
        self.assertEqual(parse_seek_time("30"), 30.0)
        self.assertEqual(parse_seek_time("1800"), 1800.0)
        # mm:ss
        self.assertEqual(parse_seek_time("05:30"), 330.0)
        # hh:mm:ss.ms
        self.assertEqual(parse_seek_time("01:02:03"), 3723.0)
        self.assertAlmostEqual(parse_seek_time("00:01:05.500"), 65.5)

    def test_basic_switches(self):
        args = ["jonaki", "movie.mkv", "/filedlg", "/autoplay", "/new", "/volume=75"]
        opts = parse_arguments(args)
        self.assertEqual(opts["contents"], ["movie.mkv"])
        self.assertTrue(opts["filedlg"])
        self.assertTrue(opts["autoplay"])
        self.assertTrue(opts["new"])
        self.assertEqual(opts["volume"], 75.0)

    def test_sub_and_aud_switches(self):
        args = ["jonaki", "video.mp4", '/sub="subs.srt"', '/aud="audio.m4a"', "/seek=00:10:00"]
        opts = parse_arguments(args)
        self.assertEqual(opts["contents"], ["video.mp4"])
        self.assertEqual(opts["sub"], "subs.srt")
        self.assertEqual(opts["aud"], "audio.m4a")
        self.assertEqual(opts["seek"], 600.0)

    def test_network_and_headers_switches(self):
        args = ["jonaki", "https://stream.m3u8", '/user_agent="MyPlayer"', '/referer="https://site.com"']
        opts = parse_arguments(args)
        self.assertEqual(opts["contents"], ["https://stream.m3u8"])
        self.assertEqual(opts["user_agent"], "MyPlayer")
        self.assertEqual(opts["referer"], "https://site.com")

    def test_stdin_streaming_switch(self):
        args = ["jonaki", "-"]
        opts = parse_arguments(args)
        self.assertTrue(opts["stdin_stream"])
        self.assertIn("fd://0", opts["contents"])

    def test_absolute_linux_paths(self):
        args = ["jonaki", "/home/ashik/movie.mkv", "/volume=80", "/seek=00:01:00"]
        opts = parse_arguments(args)
        self.assertIn("/home/ashik/movie.mkv", opts["contents"])
        self.assertEqual(opts["volume"], 80.0)
        self.assertEqual(opts["seek"], 60.0)

    def test_volume_clamp(self):
        opts1 = parse_arguments(["jonaki", "/volume=150"])
        self.assertEqual(opts1["volume"], 100.0)
        opts2 = parse_arguments(["jonaki", "/volume=-20"])
        self.assertEqual(opts2["volume"], 0.0)


if __name__ == "__main__":
    unittest.main()
