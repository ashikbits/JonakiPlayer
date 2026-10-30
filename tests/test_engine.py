"""
Unit tests for JonakiCore packed in-process libmpv media engine.
"""

import unittest
import unittest.mock
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from core.engine import JonakiCore, PlaybackState


class TestJonakiCore(unittest.TestCase):
    def setUp(self):
        self.core = JonakiCore()

    def tearDown(self):
        self.core.stop_engine()

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
        # BUG 2.2: Test full A-B repeat loop logic including Point B validation and tick seeking
        self.core.position = 10.0
        self.core.set_repeat_point_a()
        self.assertEqual(self.core.repeat_a, 10.0)

        # Setting Point B before/at Point A must be rejected
        self.core.position = 5.0
        res = self.core.set_repeat_point_b()
        self.assertIsNone(res)
        self.assertIsNone(self.core.repeat_b)

        # Setting Point B after Point A succeeds
        self.core.position = 25.0
        self.core.set_repeat_point_b()
        self.assertEqual(self.core.repeat_b, 25.0)

        # When position exceeds repeat_b, _query_time_tick seeks back to repeat_a
        with unittest.mock.patch.object(self.core, "get_property_float", side_effect=lambda prop, default=0.0: 26.0 if prop == "time-pos" else default), \
             unittest.mock.patch.object(self.core, "seek_absolute") as mock_seek:
            self.core._query_time_tick()
            mock_seek.assert_called_with(10.0)

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
        # BUG 2.3: Verify set_aspect_ratio_mode synchronizes aspect_ratio_mode cycle index
        self.core.set_aspect_ratio_mode("16:9")
        self.assertEqual(self.core.aspect_ratio_mode, 2)
        val1 = float(self.core.get_property("video-aspect-override") or 0)
        self.assertAlmostEqual(val1, 16.0 / 9.0, places=3)

        self.core.set_aspect_ratio_mode("2.35:1")
        self.assertEqual(self.core.aspect_ratio_mode, 4)
        val2 = float(self.core.get_property("video-aspect-override") or 0)
        self.assertAlmostEqual(val2, 2.35, places=2)

    def test_media_detailed_info_structure(self):
        # BUG 2.1: Verify detailed info structure on both idle and active playback mock
        info = self.core.get_media_detailed_info()
        self.assertIsInstance(info, dict)
        self.assertIn("path", info)
        self.assertIn("duration_sec", info)
        self.assertIn("video_codec", info)
        self.assertIn("audio_codec", info)
        self.assertIn("tracks", info)

        # Active playback metadata resolution
        self.core.current_file = "/media/test_movie.mkv"
        self.core.current_title = "test_movie.mkv"
        self.core.duration = 7200.0
        self.core.video_width = 1920
        self.core.video_height = 1080
        self.core.video_codec = "HEVC"
        self.core.audio_codec = "EAC3"

        info_active = self.core.get_media_detailed_info()
        self.assertEqual(info_active["path"], "/media/test_movie.mkv")
        self.assertEqual(info_active["width"], 1920)
        self.assertEqual(info_active["height"], 1080)
        self.assertEqual(info_active["video_codec"], "HEVC")
        self.assertEqual(info_active["audio_codec"], "EAC3")

    def test_equalizer_bands_clamped(self):
        self.core.set_equalizer_band(0, 20.0)
        self.assertEqual(self.core.equalizer_bands[0], 12.0)
        self.core.set_equalizer_band(0, -20.0)
        self.assertEqual(self.core.equalizer_bands[0], -12.0)

    def test_hwdec_toggle(self):
        initial = self.core.hwdec_active
        self.core.toggle_hwdec()
        self.assertEqual(self.core.hwdec_active, "no")
        self.core.toggle_hwdec()
        self.assertEqual(self.core.hwdec_active, initial)

    def test_video_fps_default(self):
        self.assertEqual(self.core.video_fps, 0.0)

    def test_ab_repeat_validation(self):
        # BUG 1.2: Setting point A past point B invalidates point B to avoid infinite seek loop
        self.core.position = 30.0
        self.core.repeat_b = 20.0
        self.core.set_repeat_point_a()
        self.assertEqual(self.core.repeat_a, 30.0)
        self.assertIsNone(self.core.repeat_b)

    def test_stop_resets_metadata(self):
        # BUG 1.17: stop() must reset current_file, duration, and video dimensions
        self.core.current_file = "/media/test.mkv"
        self.core.current_title = "test.mkv"
        self.core.duration = 120.0
        self.core.position = 45.0
        self.core.video_width = 1920
        self.core.video_height = 1080
        self.core.stop()

        self.assertIsNone(self.core.current_file)
        self.assertIsNone(self.core.current_title)
        self.assertEqual(self.core.duration, 0.0)
        self.assertEqual(self.core.position, 0.0)
        self.assertEqual(self.core.video_width, 0)
        self.assertEqual(self.core.video_height, 0)
        self.assertEqual(self.core.state, PlaybackState.STOPPED)

    def test_flip_toggles_internal_state(self):
        # BUG 1.14: Flip toggles maintain predictable internal state
        self.assertFalse(self.core.is_horizontal_flip_active())
        self.assertTrue(self.core.toggle_horizontal_flip())
        self.assertTrue(self.core.is_horizontal_flip_active())
        self.assertFalse(self.core.toggle_horizontal_flip())
        self.assertFalse(self.core.is_horizontal_flip_active())

    def test_eof_handling_under_keep_open(self):
        # BUG 1.1: When eof is reached under keep-open=yes, core triggers on_file_end
        self.core.current_file = "/media/test.mp4"
        self.core.state = PlaybackState.PAUSED  # libmpv pauses at EOF when keep-open=yes
        file_ended = []
        self.core.on_file_end = lambda: file_ended.append(True)

        with unittest.mock.patch.object(self.core, "get_property", side_effect=lambda k: "yes" if k == "eof-reached" else None):
            self.core._query_time_tick()

        self.assertEqual(file_ended, [True])
        self.assertEqual(self.core.state, PlaybackState.STOPPED)

    def test_playback_controls_and_callbacks(self):
        # BUG 2.4: Test play, pause, play_pause, seek, audio/sub track commands, and callbacks
        state_changes = []
        time_updates = []
        self.core.on_state_change = lambda st: state_changes.append(st)
        self.core.on_time_update = lambda p, d: time_updates.append((p, d))

        # Play / Pause / PlayPause
        self.core.play()
        self.assertEqual(self.core.state, PlaybackState.PLAYING)
        self.assertIn(PlaybackState.PLAYING, state_changes)

        self.core.pause()
        self.assertEqual(self.core.state, PlaybackState.PAUSED)
        self.assertIn(PlaybackState.PAUSED, state_changes)

        self.core.play_pause()
        self.assertEqual(self.core.state, PlaybackState.PLAYING)

        self.core.play_pause()
        self.assertEqual(self.core.state, PlaybackState.PAUSED)

        # Seeking operations
        with unittest.mock.patch.object(self.core, "command") as mock_cmd:
            self.core.seek_relative(10.0)
            mock_cmd.assert_called_with("seek 10.0 relative")

            self.core.seek_absolute(120.0)
            mock_cmd.assert_called_with("seek 120.0 absolute")

            self.core.seek_percent(50.0)
            mock_cmd.assert_called_with("seek 50.0 absolute-percent")

            self.core.cycle_subtitle_track()
            mock_cmd.assert_called_with("cycle sub")

            self.core.cycle_audio_track()
            mock_cmd.assert_called_with("cycle audio")

        # Callbacks invocation via tick
        with unittest.mock.patch.object(self.core, "get_property_float", side_effect=lambda prop, default=0.0: 15.0 if prop == "time-pos" else (100.0 if prop == "duration" else default)):
            self.core._query_time_tick()
        self.assertIn((15.0, 100.0), time_updates)

        # Audio delay, HDR toggle, speed
        self.core.set_audio_delay(0.15)
        self.assertEqual(self.core.audio_delay_sec, 0.15)

        self.assertFalse(self.core.hdr_active)
        self.core.toggle_hdr()
        self.assertTrue(self.core.hdr_active)

        self.core.set_speed(1.5)
        self.assertEqual(self.core.speed, 1.5)

    def test_video_scaling_and_zoom(self):
        """Test independent video height/width scaling, zoom, clamping, and reset."""
        import math
        # Initial defaults
        self.assertEqual(self.core.video_scale_x, 1.0)
        self.assertEqual(self.core.video_scale_y, 1.0)
        self.assertEqual(self.core.video_zoom, 1.0)

        # Height scaling
        new_h = self.core.scale_video_height(+0.05)
        self.assertEqual(new_h, 1.05)
        self.assertEqual(self.core.video_scale_y, 1.05)
        # Verify independence: width and zoom unchanged
        self.assertEqual(self.core.video_scale_x, 1.0)
        self.assertEqual(self.core.video_zoom, 1.0)

        # Height decrement
        new_h = self.core.scale_video_height(-0.10)
        self.assertEqual(new_h, 0.95)

        # Height limits: max 3.0, min 0.2
        for _ in range(50):
            self.core.scale_video_height(+0.1)
        self.assertEqual(self.core.video_scale_y, 3.0)
        for _ in range(50):
            self.core.scale_video_height(-0.1)
        self.assertEqual(self.core.video_scale_y, 0.2)

        # Width scaling
        new_w = self.core.scale_video_width(+0.05)
        self.assertEqual(new_w, 1.05)
        self.assertEqual(self.core.video_scale_x, 1.05)
        # Width limits: max 3.0, min 0.2
        for _ in range(50):
            self.core.scale_video_width(+0.1)
        self.assertEqual(self.core.video_scale_x, 3.0)
        for _ in range(50):
            self.core.scale_video_width(-0.1)
        self.assertEqual(self.core.video_scale_x, 0.2)

        # Zoom scaling
        new_z = self.core.zoom_video(+0.05)
        self.assertEqual(new_z, 1.05)
        self.assertEqual(self.core.video_zoom, 1.05)
        # Zoom limits: max 4.0, min 0.2
        for _ in range(70):
            self.core.zoom_video(+0.1)
        self.assertEqual(self.core.video_zoom, 4.0)
        for _ in range(50):
            self.core.zoom_video(-0.1)
        self.assertEqual(self.core.video_zoom, 0.2)

        # Reset dimensions
        self.core.reset_video_dimensions()
        self.assertEqual(self.core.video_scale_x, 1.0)
        self.assertEqual(self.core.video_scale_y, 1.0)
        self.assertEqual(self.core.video_zoom, 1.0)
        self.assertEqual(self.core.get_property("video-scale-x"), "1.000000")
        self.assertEqual(self.core.get_property("video-scale-y"), "1.000000")
        self.assertEqual(self.core.get_property("video-zoom"), "0.000000")


if __name__ == "__main__":
    unittest.main()
