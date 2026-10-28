"""
Unit tests for PotPlayer DSF skin engine.
"""

import unittest
import sys
import os
import cairo

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from ui.skin_engine import PotSkinEngine, SkinButton, SkinSlider, clean_codec_name


class TestPotSkinEngine(unittest.TestCase):
    def test_skin_loading(self):
        dsf_path = os.path.join(os.path.dirname(__file__), "..", "assets", "skins", "Default.dsf")
        skin = PotSkinEngine(dsf_path)
        self.assertIn("Main.png", skin.surfaces)
        self.assertIsNotNone(skin.timebar)
        self.assertIsNotNone(skin.volume_slider)
        self.assertTrue(len(skin.buttons) > 0)
        self.assertTrue(len(skin.badges) > 0)

    def test_hit_testing(self):
        skin = PotSkinEngine()
        skin.layout(800, 62)
        # Test hitting the play button when not playing
        play_btn = skin.btn_play
        bx, by, bw, bh = play_btn.rect
        hit = skin.hit_test(bx + 5, by + 5, is_playing=False)
        self.assertEqual(hit, play_btn)

        # BUG 6.2: Test hitting the pause button when is_playing=True
        pause_btn = skin.btn_pause
        hit_pause = skin.hit_test(bx + 5, by + 5, is_playing=True)
        self.assertEqual(hit_pause, pause_btn)

        # Test hitting the stop button
        stop_btn = skin.btn_stop
        hit_stop = skin.hit_test(stop_btn.rect[0] + 5, stop_btn.rect[1] + 5)
        self.assertEqual(hit_stop, stop_btn)

        # Test hitting the mute button
        mute_btn = skin.btn_mute
        hit_mute = skin.hit_test(mute_btn.rect[0] + 2, mute_btn.rect[1] + 2)
        self.assertEqual(hit_mute, mute_btn)

        # Test hitting the timebar slider
        timebar = skin.timebar
        hit_tb = skin.hit_test(timebar.rect[0] + 20, timebar.rect[1] + 2)
        self.assertEqual(hit_tb, timebar)

        # Test hitting the volume slider
        vol = skin.volume_slider
        hit_vol = skin.hit_test(vol.rect[0] + 10, vol.rect[1] + 2)
        self.assertEqual(hit_vol, vol)

    def test_codec_name_cleaner(self):
        self.assertEqual(clean_codec_name("AOMedia Video 1 (AV1)"), "AV1")
        self.assertEqual(clean_codec_name("H.264 / AVC"), "H264")
        self.assertEqual(clean_codec_name("HEVC / H.265"), "HEVC")
        self.assertEqual(clean_codec_name("Opus"), "OPUS")
        self.assertEqual(clean_codec_name("MPEG-4 AAC"), "AAC")
        self.assertEqual(clean_codec_name("FLAC"), "FLAC")

    def test_render_surface(self):
        skin = PotSkinEngine()
        surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, 960, 62)
        cr = cairo.Context(surf)
        info = {
            "hwdec": "vaapi",
            "hdr": True,
            "video_codec": "AV1",
            "audio_codec": "OPUS",
            "audio_channels": 2,
            "is_muted": False
        }
        # Render without crashing
        skin.render(cr, 960, 62, is_playing=True, position_sec=120.0, duration_sec=300.0,
                    repeat_a=10.0, repeat_b=50.0, bookmarks=[30.0, 90.0], media_info=info)
        self.assertEqual(surf.get_width(), 960)
        self.assertEqual(surf.get_height(), 62)
        # BUG 6.1: Verify actual drawing occurred by checking pixel buffer contains non-zero bytes
        self.assertTrue(any(b != 0 for b in surf.get_data()))


if __name__ == "__main__":
    unittest.main()
