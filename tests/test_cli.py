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
        # Negative, empty, or malformed tokens must return 0.0
        self.assertEqual(parse_seek_time("-10"), 0.0)
        self.assertEqual(parse_seek_time(""), 0.0)
        self.assertEqual(parse_seek_time("invalid_token"), 0.0)
        self.assertEqual(parse_seek_time("00:invalid:10"), 0.0)

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
        # BUG 1.2: Assert /headers switch alongside /user_agent and /referer
        args = ["jonaki", "https://stream.m3u8", '/user_agent="MyPlayer"', '/referer="https://site.com"', '/headers="X-Auth: 123"']
        opts = parse_arguments(args)
        self.assertEqual(opts["contents"], ["https://stream.m3u8"])
        self.assertEqual(opts["user_agent"], "MyPlayer")
        self.assertEqual(opts["referer"], "https://site.com")
        self.assertEqual(opts["headers"], "X-Auth: 123")

    def test_stdin_streaming_switch(self):
        args = ["jonaki", "-"]
        opts = parse_arguments(args)
        self.assertTrue(opts["stdin_stream"])
        self.assertIn("fd://0", opts["contents"])

    def test_absolute_linux_paths(self):
        dummy_path = "/tmp/nonexistent_test_movie_12345.mkv"
        args = ["jonaki", dummy_path, "/volume=80", "/seek=00:01:00"]
        opts = parse_arguments(args)
        self.assertIn(dummy_path, opts["contents"])
        self.assertEqual(opts["volume"], 80.0)
        self.assertEqual(opts["seek"], 60.0)

    def test_volume_clamp_and_invalid(self):
        opts1 = parse_arguments(["jonaki", "/volume=150"])
        self.assertEqual(opts1["volume"], 100.0)
        opts2 = parse_arguments(["jonaki", "/volume=-20"])
        self.assertEqual(opts2["volume"], 0.0)
        # BUG 1.4: Non-numeric volume should be ignored without raising exception
        opts3 = parse_arguments(["jonaki", "/volume=invalid"])
        self.assertIsNone(opts3["volume"])

    def test_additional_cli_switches(self):
        # BUG 1.4: Comprehensive coverage for all supported PotPlayer CLI switches
        args = [
            "jonaki",
            "/urldlg",
            "/folderdlg",
            "/simple",
            "/cap",
            "/cam",
            "/dvd",
            "/cd:1",
            "/add",
            "/insert",
            "/same",
            "/sort",
            "/randomize",
            "/current",
            "/clipboard",
            '/title="Custom Title"',
            '/config="Cinema"'
        ]
        opts = parse_arguments(args)
        self.assertTrue(opts["urldlg"])
        self.assertTrue(opts["folderdlg"])
        self.assertTrue(opts["simple"])
        self.assertTrue(opts["cap"])
        self.assertTrue(opts["cam"])
        self.assertTrue(opts["dvd"])
        self.assertEqual(opts["cd"], "1")
        self.assertTrue(opts["add"])
        self.assertTrue(opts["insert"])
        self.assertTrue(opts["same"])
        self.assertTrue(opts["sort"])
        self.assertTrue(opts["randomize"])
        self.assertTrue(opts["current"])
        self.assertTrue(opts["clipboard"])
        self.assertEqual(opts["title"], "Custom Title")
        self.assertEqual(opts["config"], "Cinema")

    def test_torrent_switches(self):
        magnet = "magnet:?xt=urn:btih:da39a3ee5e6b4b0d3255bfef95601890afd80709&dn=test"
        args = ["jonaki", "/torrentdlg", magnet]
        opts = parse_arguments(args)
        self.assertTrue(opts["torrentdlg"])
        self.assertIn(magnet, opts["contents"])


if __name__ == "__main__":
    unittest.main()
