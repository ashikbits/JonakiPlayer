"""
Unit tests for JonakiCore packed in-process libmpv media engine.
"""

import unittest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from core.engine import JonakiCore, PotPlayerCore, PlaybackState


class TestJonakiCore(unittest.TestCase):
    def setUp(self):
        self.core = JonakiCore()

    def tearDown(self):
        self.core.stop_engine()

    def test_alias_compatibility(self):
        self.assertIs(PotPlayerCore, JonakiCore)

    def test_pipeline_initialization(self):
        self.assertIsNotNone(self.core.handle)
        self.assertIsNotNone(self.core.lib)
        self.assertEqual(self.core.state, PlaybackState.IDLE)

    def test_volume_and_mute(self):
        self.core.set_volume(80.0)
        self.assertEqual(self.core.volume, 80.0)
        self.core.set_mute(True)
        self.assertTrue(self.core.is_muted)
        self.core.toggle_mute()
        self.assertFalse(self.core.is_muted)

    def test_equalizer_bands(self):
        self.core.set_equalizer_band(0, 5.0)
        self.assertEqual(self.core.equalizer_bands[0], 5.0)
        self.assertIn("equalizer", self.core.get_property("af") or "")

        # Boundary clamping (-24 to 12 dB)
        self.core.set_equalizer_band(1, 30.0)
        self.assertEqual(self.core.equalizer_bands[1], 12.0)

    def test_video_colors_mapping(self):
        self.core.set_video_colors(brightness=10, contrast=20, saturation=-5, hue=0)
        self.assertEqual(self.core.brightness, 10.0)
        self.assertEqual(self.core.contrast, 20.0)
        self.assertEqual(self.core.saturation, -5.0)

    def test_ab_repeat_points(self):
        self.core.position = 10.0
        self.core.set_repeat_point_a()
        self.assertEqual(self.core.repeat_a, 10.0)

        self.core.position = 25.0
        self.core.set_repeat_point_b()
        self.assertEqual(self.core.repeat_b, 25.0)

        self.core.clear_repeat()
        self.assertIsNone(self.core.repeat_a)
        self.assertIsNone(self.core.repeat_b)

    def test_aspect_ratio_and_rotation(self):
        lbl = self.core.cycle_aspect_ratio()
        self.assertEqual(lbl, "Stretch to Window")
        lbl2 = self.core.cycle_aspect_ratio()
        self.assertIn("16:9", lbl2)

        rot_lbl = self.core.rotate_video()
        self.assertIn("90°", rot_lbl)
        self.assertEqual(self.core.get_property("video-rotate"), "90")

    def test_audio_boost_and_normalizer(self):
        self.core.set_audio_boost(6.0)
        self.assertAlmostEqual(self.core.audio_boost_db, 6.0)
        self.assertIn("volume=", self.core.get_property("af") or "")

        self.core.set_normalizer(True)
        self.assertTrue(self.core.normalizer_active)
        self.assertIn("dynaudnorm", self.core.get_property("af") or "")

        self.core.set_normalizer(False)
        self.assertFalse(self.core.normalizer_active)

    def test_volume_clamp_100(self):
        self.core.set_volume(150.0)
        self.assertEqual(self.core.volume, 100.0)

        self.core.set_volume(-20.0)
        self.assertEqual(self.core.volume, 0.0)

    def test_toggle_stretch(self):
        msg1 = self.core.toggle_stretch()
        self.assertIn("Stretch", msg1)

        msg2 = self.core.toggle_stretch()
        self.assertIn("Keep Aspect Ratio", msg2)

    def test_subtitle_delay(self):
        self.core.set_subtitle_delay(1.5)
        self.assertEqual(self.core.subtitle_delay_sec, 1.5)
        self.assertIn("1.5", self.core.get_property("sub-delay") or "")

    def test_speed_controls(self):
        self.core.set_speed(1.5)
        self.assertEqual(self.core.speed, 1.5)
        self.assertIn("1.5", self.core.get_property("speed") or "")

        self.core.set_speed(0.05)  # Clamps to min 0.1
        self.assertEqual(self.core.speed, 0.1)

    def test_subtitle_pos_and_size(self):
        self.core.adjust_subtitle_pos(5)
        self.assertEqual(self.core.sub_pos, 105)
        self.assertAlmostEqual(float(self.core.get_property("sub-pos") or 0), 105.0)

        self.core.set_subtitle_font_size(42)
        self.assertEqual(self.core.sub_size, 42)
        self.assertAlmostEqual(float(self.core.get_property("sub-font-size") or 0), 42.0)

    def test_video_effects_toggles(self):
        self.core.toggle_deinterlace()
        self.assertTrue(self.core.deinterlace_active)
        self.assertEqual(self.core.get_property("deinterlace"), "yes")

        self.core.toggle_deband()
        self.assertTrue(self.core.deband_active)
        self.assertEqual(self.core.get_property("deband"), "yes")

    def test_video_flips(self):
        # Horizontal flip
        self.assertFalse(self.core.is_horizontal_flip_active())
        h_active = self.core.toggle_horizontal_flip()
        self.assertTrue(h_active)
        self.assertTrue(self.core.is_horizontal_flip_active())
        h_active = self.core.toggle_horizontal_flip()
        self.assertFalse(h_active)
        self.assertFalse(self.core.is_horizontal_flip_active())

        # Vertical flip
        self.assertFalse(self.core.is_vertical_flip_active())
        v_active = self.core.toggle_vertical_flip()
        self.assertTrue(v_active)
        self.assertTrue(self.core.is_vertical_flip_active())
        v_active = self.core.toggle_vertical_flip()
        self.assertFalse(v_active)
        self.assertFalse(self.core.is_vertical_flip_active())

        # Reset orientation
        self.core.toggle_horizontal_flip()
        self.core.rotate_video()
        self.core.reset_video_orientation()
        self.assertFalse(self.core.is_horizontal_flip_active())
        self.assertEqual(self.core.video_rotation_index, 0)

    def test_track_properties_and_selection(self):
        # aid
        self.core.set_audio_track("no")
        self.assertEqual(self.core.get_current_audio_track_id(), "no")
        self.core.set_audio_track("auto")
        self.assertEqual(self.core.get_current_audio_track_id(), "auto")

        # sid
        self.core.set_subtitle_track("no")
        self.assertEqual(self.core.get_current_subtitle_track_id(), "no")
        self.core.set_subtitle_track("auto")
        self.assertEqual(self.core.get_current_subtitle_track_id(), "auto")

        # secondary-sid (dual subtitles)
        self.core.set_secondary_subtitle_track("no")
        self.assertEqual(self.core.get_current_secondary_subtitle_track_id(), "no")

    def test_aspect_ratio_presets(self):
        self.core.set_aspect_ratio_mode("16:9")
        val1 = float(self.core.get_property("video-aspect-override") or 0)
        self.assertAlmostEqual(val1, 16.0 / 9.0, places=3)

        self.core.set_aspect_ratio_mode("2.35:1")
        val2 = float(self.core.get_property("video-aspect-override") or 0)
        self.assertAlmostEqual(val2, 2.35, places=2)

    def test_media_detailed_info_structure(self):
        info = self.core.get_media_detailed_info()
        self.assertIsInstance(info, dict)
        self.assertIn("path", info)
        self.assertIn("duration_sec", info)
        self.assertIn("video_codec", info)
        self.assertIn("audio_codec", info)
        self.assertIn("tracks", info)


if __name__ == "__main__":
    unittest.main()
