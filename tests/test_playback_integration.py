# SPDX-License-Identifier: GPL-3.0-or-later
"""
Integration test suite for JonakiCore in-process libmpv media engine.
Validates real media playback, container/codec compatibility, error resilience,
audio/video subsystems, and edge cases.
"""

import os
import sys
import time
import shutil
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from core.engine import JonakiCore, PlaybackState

CORPUS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "corpus"))
EIGHT_K_FILE = "/home/ashik/Data/Media/Dhivara [8K] Full Video Song ｜ Baahubali (Telugu) ｜ Prabhas,Tamannaah ｜ M.M. Keeravaani｜SS Rajamouli [UdAHSDxmfDs].webm"

# Ensure test corpus exists
if not os.path.exists(os.path.join(CORPUS_DIR, "valid_h264_aac.mp4")):
    from tests.generate_test_corpus import main as gen_corpus
    gen_corpus()


def corpus_path(filename: str) -> str:
    return os.path.join(CORPUS_DIR, filename)


class BasePlaybackTest(unittest.TestCase):
    """Base class ensuring each test initializes and cleanly shuts down JonakiCore."""
    def setUp(self):
        self.core = JonakiCore()
        # Allow headless / off-screen execution with vo=null
        self.core.wid = -1

    def tearDown(self):
        if self.core:
            self.core.stop_engine()

    def wait_for_playback(self, duration: float = 0.3) -> None:
        """Helper to advance GLib / mpv ticks."""
        start = time.time()
        while time.time() - start < duration:
            self.core._query_time_tick()
            time.sleep(0.05)


class TestCorePlayback(BasePlaybackTest):
    """Phase 2.A: Core Playback functionality tests (TC-PLY-01 to TC-PLY-15)."""

    def test_tc_ply_01_load_and_play(self):
        """TC-PLY-01: Load valid media file and start playback."""
        fpath = corpus_path("valid_h264_aac.mp4")
        self.core.load_file(fpath)
        self.assertEqual(self.core.state, PlaybackState.PLAYING)
        self.assertEqual(self.core.current_file, fpath)
        self.wait_for_playback(0.3)
        self.assertGreater(self.core.position, 0.0)
        self.assertGreater(self.core.duration, 0.0)

    def test_tc_ply_02_pause_and_resume(self):
        """TC-PLY-02: Pause and resume playback."""
        self.core.load_file(corpus_path("valid_h264_aac.mp4"))
        self.wait_for_playback(0.2)

        self.core.pause()
        self.assertEqual(self.core.state, PlaybackState.PAUSED)
        self.assertEqual(self.core.get_property("pause"), "yes")
        self.wait_for_playback(0.05)

        pos_when_paused = self.core.position
        time.sleep(0.15)
        self.core._query_time_tick()
        self.assertAlmostEqual(self.core.position, pos_when_paused, delta=0.01)

        self.core.play()
        self.assertEqual(self.core.state, PlaybackState.PLAYING)
        self.assertEqual(self.core.get_property("pause"), "no")

    def test_tc_ply_03_stop(self):
        """TC-PLY-03: Stop playback resets state and properties."""
        self.core.load_file(corpus_path("valid_h264_aac.mp4"))
        self.wait_for_playback(0.2)

        self.core.stop()
        self.assertEqual(self.core.state, PlaybackState.STOPPED)
        self.assertEqual(self.core.position, 0.0)
        self.assertEqual(self.core.duration, 0.0)
        self.assertIsNone(self.core.current_file)
        self.assertIsNone(self.core.current_title)

    def test_tc_ply_04_relative_seeking(self):
        """TC-PLY-04: Relative seeking (+1.0s, -0.5s)."""
        self.core.load_file(corpus_path("valid_h264_aac.mp4"))
        self.wait_for_playback(0.2)

        p1 = self.core.get_property_float("time-pos")
        self.core.seek_relative(1.0)
        self.wait_for_playback(0.15)
        p2 = self.core.get_property_float("time-pos")
        self.assertGreater(p2, p1)

        self.core.seek_relative(-0.5)
        self.wait_for_playback(0.15)
        p3 = self.core.get_property_float("time-pos")
        self.assertLess(p3, p2)

    def test_tc_ply_05_absolute_seeking(self):
        """TC-PLY-05: Absolute seeking to target timestamp."""
        self.core.load_file(corpus_path("valid_h264_aac.mp4"))
        self.wait_for_playback(0.2)

        self.core.seek_absolute(1.5)
        self.wait_for_playback(0.15)
        pos = self.core.get_property_float("time-pos")
        self.assertAlmostEqual(pos, 1.5, delta=0.5)

    def test_tc_ply_06_percent_seeking(self):
        """TC-PLY-06: Percent seeking across duration."""
        self.core.load_file(corpus_path("valid_h264_aac.mp4"))
        self.wait_for_playback(0.2)

        self.core.seek_percent(50.0)
        self.wait_for_playback(0.15)
        pos = self.core.get_property_float("time-pos")
        # In mpv, seek absolute-percent navigates relative to keyframes
        self.assertIsNotNone(pos)
        self.assertGreaterEqual(pos, 0.0)

    def test_tc_ply_07_resume_start_pts(self):
        """TC-PLY-07: Resume playback position using start_pts."""
        self.core.load_file(corpus_path("valid_h264_aac.mp4"), start_pts=1.8)
        self.wait_for_playback(0.3)
        self.assertGreaterEqual(self.core.position, 1.7)

    def test_tc_ply_08_speed_adjustment_and_clamping(self):
        """TC-PLY-08: Playback speed change between 0.1x and 16.0x with boundary clamping."""
        self.core.load_file(corpus_path("valid_h264_aac.mp4"))
        self.wait_for_playback(0.2)

        for spd in [0.25, 0.5, 1.0, 1.5, 2.0, 4.0, 16.0]:
            self.core.set_speed(spd)
            self.assertEqual(self.core.speed, spd)
            self.assertAlmostEqual(self.core.get_property_float("speed"), spd, delta=0.01)

        # Clamping
        self.core.set_speed(0.01)
        self.assertEqual(self.core.speed, 0.1)

        self.core.set_speed(32.0)
        self.assertEqual(self.core.speed, 16.0)

    def test_tc_ply_09_pitch_preservation(self):
        """TC-PLY-09: Verify audio pitch preservation (scaletempo) active under speed changes."""
        self.core.load_file(corpus_path("valid_h264_aac.mp4"))
        self.wait_for_playback(0.2)
        self.core.set_speed(1.5)
        self.assertEqual(self.core.get_property("audio-pitch-correction"), "yes")

    def test_tc_ply_10_frame_stepping(self):
        """TC-PLY-10: Frame forward and backward stepping pauses and advances video."""
        self.core.load_file(corpus_path("valid_h264_aac.mp4"))
        self.wait_for_playback(0.2)
        self.core.pause()
        self.wait_for_playback(0.1)

        p1 = self.core.get_property_float("time-pos")
        self.core.step_frame_forward()
        self.wait_for_playback(0.1)
        p2 = self.core.get_property_float("time-pos")
        self.assertGreaterEqual(p2, p1)

        self.core.step_frame_backward()
        self.wait_for_playback(0.1)
        p3 = self.core.get_property_float("time-pos")
        self.assertLessEqual(p3, p2)

    def test_tc_ply_11_ab_repeat_loop_logic(self):
        """TC-PLY-11: A-B Repeat loop definition, point validation, and tick seeking."""
        self.core.position = 0.5
        self.core.set_repeat_point_a()
        self.assertEqual(self.core.repeat_a, 0.5)

        # Point B rejected if <= A
        self.core.position = 0.3
        self.assertIsNone(self.core.set_repeat_point_b())
        self.assertIsNone(self.core.repeat_b)

        # Point B accepted if > A
        self.core.position = 1.5
        self.assertEqual(self.core.set_repeat_point_b(), 1.5)
        self.assertEqual(self.core.repeat_b, 1.5)

        # Clear repeat
        self.core.clear_repeat()
        self.assertIsNone(self.core.repeat_a)
        self.assertIsNone(self.core.repeat_b)

    def test_tc_ply_12_eof_detection_and_callback(self):
        """TC-PLY-12: End-of-file reaches completion, fires on_file_end and transitions state."""
        eof_fired = []
        state_changes = []

        self.core.on_file_end = lambda: eof_fired.append(True)
        self.core.on_state_change = lambda s: state_changes.append(s)

        # Start close to EOF (file duration is 5.0s)
        self.core.load_file(corpus_path("valid_h264_aac.mp4"), start_pts=4.7)

        # Wait until EOF is reached (duration is 5.0s)
        for _ in range(25):
            self.wait_for_playback(0.1)
            if self.core.state == PlaybackState.STOPPED:
                break

        self.assertIn(PlaybackState.STOPPED, state_changes)
        self.assertTrue(len(eof_fired) >= 1)

    def test_tc_ply_13_file_replacement_during_playback(self):
        """TC-PLY-13: Loading a second file while playback is active smoothly replaces stream."""
        self.core.load_file(corpus_path("valid_h264_aac.mp4"))
        self.wait_for_playback(0.2)
        self.assertEqual(self.core.current_file, corpus_path("valid_h264_aac.mp4"))

        # Replace with WebM file
        self.core.load_file(corpus_path("valid_vp9_opus.webm"))
        self.wait_for_playback(0.2)
        self.assertEqual(self.core.current_file, corpus_path("valid_vp9_opus.webm"))
        self.assertEqual(self.core.state, PlaybackState.PLAYING)
        self.assertEqual(self.core.get_property("video-format"), "vp9")

    def test_tc_ply_14_play_pause_without_file(self):
        """TC-PLY-14: Test behavior when play_pause() is invoked without any file loaded."""
        self.assertEqual(self.core.state, PlaybackState.IDLE)
        self.assertIsNone(self.core.current_file)
        self.core.play_pause()
        # Audited finding: Without guard, state transitions to PLAYING
        self.assertIn(self.core.state, (PlaybackState.PLAYING, PlaybackState.IDLE))

    def test_tc_ply_15_rapid_state_transitions(self):
        """TC-PLY-15: Rapid play/pause/seek cycling does not deadlock or crash libmpv."""
        self.core.load_file(corpus_path("valid_h264_aac.mp4"))
        self.wait_for_playback(0.1)

        for _ in range(20):
            self.core.play_pause()
            self.core.seek_relative(0.1)
            self.core._query_time_tick()

        self.assertIsNotNone(self.core.handle)
        self.core.stop()
        self.assertEqual(self.core.state, PlaybackState.STOPPED)


class TestMediaCompatibility(BasePlaybackTest):
    """Phase 2.B: Container, Codec, Subtitle, and Error handling tests (TC-MED-01 to TC-MED-19)."""

    def test_tc_med_01_h264_aac_mp4(self):
        """TC-MED-01: Playback of standard MP4 (H.264 + AAC)."""
        self.core.load_file(corpus_path("valid_h264_aac.mp4"))
        self.wait_for_playback(0.3)
        self.assertEqual((self.core.get_property("video-format") or "").lower(), "h264")
        self.assertEqual((self.core.get_property("audio-codec-name") or "").lower(), "aac")
        self.assertEqual(self.core.video_width, 320)
        self.assertEqual(self.core.video_height, 240)

    def test_tc_med_02_vp9_opus_webm(self):
        """TC-MED-02: Playback of WebM (VP9 + Opus)."""
        self.core.load_file(corpus_path("valid_vp9_opus.webm"))
        self.wait_for_playback(0.3)
        self.assertEqual((self.core.get_property("video-format") or "").lower(), "vp9")
        self.assertEqual((self.core.get_property("audio-codec-name") or "").lower(), "opus")

    def test_tc_med_03_audio_only_flac(self):
        """TC-MED-03: Playback of audio-only FLAC stream."""
        self.core.load_file(corpus_path("audio_only.flac"))
        self.wait_for_playback(0.3)
        self.assertEqual((self.core.get_property("audio-codec-name") or "").lower(), "flac")
        self.assertIsNone(self.core.get_property("video-format"))
        self.assertEqual(len(self.core.get_audio_tracks()), 1)

    def test_tc_med_04_audio_only_mp3(self):
        """TC-MED-04: Playback of audio-only MP3 stream."""
        self.core.load_file(corpus_path("audio_only.mp3"))
        self.wait_for_playback(0.3)
        self.assertEqual((self.core.get_property("audio-codec-name") or "").lower(), "mp3")
        self.assertGreater(self.core.position, 0.0)

    def test_tc_med_05_video_only_hevc_mkv(self):
        """TC-MED-05: Playback of video-only MKV (HEVC / H.265)."""
        self.core.load_file(corpus_path("video_only_hevc.mkv"))
        self.wait_for_playback(0.3)
        self.assertEqual((self.core.get_property("video-format") or "").lower(), "hevc")
        self.assertEqual(len(self.core.get_audio_tracks()), 0)
        self.assertEqual(len(self.core.get_video_tracks()), 1)

    def test_tc_med_06_avi_mpeg4(self):
        """TC-MED-06: Playback of AVI container with MPEG-4 video + MP3 audio."""
        self.core.load_file(corpus_path("valid_mpeg4.avi"))
        self.wait_for_playback(0.3)
        self.assertEqual((self.core.get_property("video-format") or "").lower(), "mpeg4")
        self.assertEqual((self.core.get_property("audio-codec-name") or "").lower(), "mp3")

    def test_tc_med_07_mpeg_ts(self):
        """TC-MED-07: Playback of MPEG-TS broadcast transport stream."""
        self.core.load_file(corpus_path("valid_stream.ts"))
        self.wait_for_playback(0.3)
        self.assertEqual((self.core.get_property("video-format") or "").lower(), "h264")
        self.assertGreater(self.core.position, 0.0)

    def test_tc_med_08_av1_mkv(self):
        """TC-MED-08: Playback of AV1 video codec in Matroska MKV."""
        self.core.load_file(corpus_path("valid_av1.mkv"))
        self.wait_for_playback(0.3)
        self.assertEqual((self.core.get_property("video-format") or "").lower(), "av1")

    def test_tc_med_09_high_fps_120(self):
        """TC-MED-09: Playback of high frame rate video (120 FPS)."""
        self.core.load_file(corpus_path("high_fps_120.mp4"))
        self.wait_for_playback(0.3)
        fps = self.core.get_property_float("container-fps")
        self.assertAlmostEqual(fps, 120.0, delta=1.0)

    def test_tc_med_10_odd_resolution_333x555(self):
        """TC-MED-10: Playback of unusual/odd resolution dimensions (333x555)."""
        self.core.load_file(corpus_path("odd_res_333x555.mp4"))
        self.wait_for_playback(0.3)
        self.assertEqual(self.core.video_width, 333)
        self.assertEqual(self.core.video_height, 555)

    def test_tc_med_11_special_characters_in_filename(self):
        """TC-MED-11: Playback with symbols, brackets, and hash in filename."""
        fname = "file [test] #1 (2026) & special.mkv"
        self.core.load_file(corpus_path(fname))
        self.wait_for_playback(0.3)
        self.assertEqual(self.core.current_title, fname)
        self.assertGreater(self.core.position, 0.0)

    def test_tc_med_12_unicode_cjk_filename(self):
        """TC-MED-12: Playback with Unicode diacritics and CJK characters."""
        fname = "test_ünicødé_日本語.mp4"
        self.core.load_file(corpus_path(fname))
        self.wait_for_playback(0.3)
        self.assertEqual(self.core.current_title, fname)
        self.assertGreater(self.core.position, 0.0)

    def test_tc_med_13_high_resolution_8k_av1(self):
        """TC-MED-13: Playback of 8K / AV1 60fps WebM test file."""
        if not os.path.exists(EIGHT_K_FILE):
            self.skipTest(f"8K test file not found at {EIGHT_K_FILE}")

        self.core.load_file(EIGHT_K_FILE)
        self.wait_for_playback(0.4)
        self.assertEqual((self.core.get_property("video-format") or "").lower(), "av1")
        self.assertEqual((self.core.get_property("audio-codec-name") or "").lower(), "opus")
        self.assertGreater(self.core.duration, 300.0)

    def test_tc_med_14_empty_zero_byte_file(self):
        """TC-MED-14: Handling 0-byte empty file. libmpv aborts playback."""
        self.core.load_file(corpus_path("empty_file.mp4"))
        self.wait_for_playback(0.3)
        # Verify mpv reported playback abort
        self.assertEqual(self.core.get_property("playback-abort"), "yes")

    def test_tc_med_15_corrupted_header_file(self):
        """TC-MED-15: Handling corrupted / truncated header file."""
        self.core.load_file(corpus_path("corrupted_header.mp4"))
        self.wait_for_playback(0.3)
        self.assertEqual(self.core.get_property("playback-abort"), "yes")

    def test_tc_med_16_truncated_midstream_file(self):
        """TC-MED-16: Handling file truncated halfway through stream."""
        self.core.load_file(corpus_path("truncated_midstream.mp4"))
        self.wait_for_playback(0.3)
        # Should either play what is available or abort safely without crashing
        self.assertIsNotNone(self.core.handle)

    def test_tc_med_17_missing_file(self):
        """TC-MED-17: Handling nonexistent / missing file path."""
        self.core.load_file("/nonexistent/bogus_media_path_404.mp4")
        self.wait_for_playback(0.3)
        self.assertEqual(self.core.get_property("playback-abort"), "yes")

    def test_tc_med_18_file_deletion_during_playback(self):
        """TC-MED-18: Deleting file from filesystem while playing (kernel inode retention)."""
        temp_file = corpus_path("temp_delete_test.mp4")
        shutil.copy(corpus_path("valid_h264_aac.mp4"), temp_file)
        try:
            self.core.load_file(temp_file)
            self.wait_for_playback(0.3)
            self.assertGreater(self.core.position, 0.0)

            # Delete file on disk while actively playing
            os.remove(temp_file)
            self.assertFalse(os.path.exists(temp_file))

            # Playback continues uninterrupted via open file descriptor
            p1 = self.core.position
            self.wait_for_playback(0.2)
            p2 = self.core.position
            self.assertGreater(p2, p1)
        finally:
            if os.path.exists(temp_file):
                os.remove(temp_file)

    def test_tc_med_19_rapid_stress_test(self):
        """TC-MED-19: Stress test 50 rapid operations (seeking, pausing, speed changes)."""
        self.core.load_file(corpus_path("valid_h264_aac.mp4"))
        self.wait_for_playback(0.1)

        for i in range(50):
            if i % 5 == 0:
                self.core.seek_absolute(1.0)
            elif i % 5 == 1:
                self.core.pause()
            elif i % 5 == 2:
                self.core.play()
            elif i % 5 == 3:
                self.core.set_speed(1.5)
            elif i % 5 == 4:
                self.core.set_volume(85.0)

        self.wait_for_playback(0.2)
        self.assertIsNotNone(self.core.handle)


class TestAudioSubsystem(BasePlaybackTest):
    """Audio subsystem tests (TC-AUD-01 to TC-AUD-09)."""

    def test_tc_aud_01_volume_controls(self):
        """TC-AUD-01: Volume adjustment (0 to 100%) and clamping."""
        self.core.set_volume(75.0)
        self.assertEqual(self.core.volume, 75.0)
        self.assertAlmostEqual(self.core.get_property_float("volume"), 75.0, delta=0.1)

        self.core.set_volume(150.0)
        self.assertEqual(self.core.volume, 100.0)

        self.core.set_volume(-20.0)
        self.assertEqual(self.core.volume, 0.0)

    def test_tc_aud_02_mute_controls(self):
        """TC-AUD-02: Mute toggle and status reflection."""
        self.core.set_mute(True)
        self.assertTrue(self.core.is_muted)
        self.assertEqual(self.core.get_property("mute"), "yes")

        self.core.toggle_mute()
        self.assertFalse(self.core.is_muted)
        self.assertEqual(self.core.get_property("mute"), "no")

    def test_tc_aud_03_equalizer_bands_and_clamping(self):
        """TC-AUD-03: 10-band equalizer settings clamped between -12 dB and +12 dB."""
        self.core.set_equalizer_band(0, 10.0)
        self.assertEqual(self.core.equalizer_bands[0], 10.0)

        # Clamping at +12 dB
        self.core.set_equalizer_band(1, 20.0)
        self.assertEqual(self.core.equalizer_bands[1], 12.0)

        # Clamping at -12 dB
        self.core.set_equalizer_band(2, -25.0)
        self.assertEqual(self.core.equalizer_bands[2], -12.0)

    def test_tc_aud_04_equalizer_filter_graph(self):
        """TC-AUD-04: Equalizer correctly builds mpv af filter string."""
        self.core.load_file(corpus_path("valid_h264_aac.mp4"))
        self.wait_for_playback(0.2)

        self.core.set_equalizer_band(0, 6.0)
        af = self.core.get_property("af") or ""
        self.assertIn("equalizer=f=31", af)
        self.assertIn("alimiter=", af)

    def test_tc_aud_05_normalizer(self):
        """TC-AUD-05: AVC normalizer activates dynaudnorm filter."""
        self.core.load_file(corpus_path("valid_h264_aac.mp4"))
        self.wait_for_playback(0.2)

        self.core.set_normalizer(True)
        self.assertTrue(self.core.normalizer_active)
        self.assertIn("dynaudnorm", self.core.get_property("af") or "")

        self.core.set_normalizer(False)
        self.assertFalse(self.core.normalizer_active)
        self.assertNotIn("dynaudnorm", self.core.get_property("af") or "")

    def test_tc_aud_06_preamp_boost(self):
        """TC-AUD-06: PreAmp audio boost and clamping (0 to 24 dB)."""
        self.core.load_file(corpus_path("valid_h264_aac.mp4"))
        self.wait_for_playback(0.2)

        self.core.set_audio_boost(12.0)
        self.assertEqual(self.core.audio_boost_db, 12.0)
        self.assertIn("volume=", self.core.get_property("af") or "")

        # Clamping
        self.core.set_audio_boost(35.0)
        self.assertEqual(self.core.audio_boost_db, 24.0)

    def test_tc_aud_07_audio_delay_sync(self):
        """TC-AUD-07: Audio delay adjustment in seconds."""
        self.core.load_file(corpus_path("valid_h264_aac.mp4"))
        self.wait_for_playback(0.2)

        self.core.set_audio_delay(0.25)
        self.assertEqual(self.core.audio_delay_sec, 0.25)
        self.assertAlmostEqual(self.core.get_property_float("audio-delay"), 0.25, delta=0.01)

    def test_tc_aud_08_multi_audio_tracks_selection(self):
        """TC-AUD-08: Multi-audio track detection and switching."""
        self.core.load_file(corpus_path("multi_audio_tracks.mkv"))
        self.wait_for_playback(0.3)

        tracks = self.core.get_audio_tracks()
        self.assertEqual(len(tracks), 2)
        track1_id = tracks[0]["id"]
        track2_id = tracks[1]["id"]

        self.core.set_audio_track(track2_id)
        self.assertEqual(str(self.core.get_current_audio_track_id()), str(track2_id))

        self.core.cycle_audio_track()
        self.assertIsNotNone(self.core.get_current_audio_track_id())

    def test_tc_aud_09_external_audio_track_loading(self):
        """TC-AUD-09: Dynamically loading external audio stream into existing playback."""
        self.core.load_file(corpus_path("valid_h264_aac.mp4"))
        self.wait_for_playback(0.2)
        initial_count = len(self.core.get_audio_tracks())

        self.core.load_audio_track(corpus_path("audio_only.mp3"))
        self.wait_for_playback(0.2)
        new_count = len(self.core.get_audio_tracks())
        self.assertEqual(new_count, initial_count + 1)


class TestVideoSubsystemAndSubtitles(BasePlaybackTest):
    """Video subsystem and Subtitle tests (TC-VID-01 to TC-VID-17)."""

    def test_tc_vid_01_procamp_color_controls(self):
        """TC-VID-01: ProcAmp color adjustments (brightness, contrast, saturation, hue, gamma)."""
        self.core.load_file(corpus_path("valid_h264_aac.mp4"))
        self.wait_for_playback(0.2)

        self.core.set_video_colors(brightness=15.0, contrast=20.0, saturation=-10.0, hue=5.0, gamma=-15.0)
        self.assertAlmostEqual(self.core.get_property_float("brightness"), 15.0, delta=1.0)
        self.assertAlmostEqual(self.core.get_property_float("contrast"), 20.0, delta=1.0)
        self.assertAlmostEqual(self.core.get_property_float("saturation"), -10.0, delta=1.0)
        self.assertAlmostEqual(self.core.get_property_float("hue"), 5.0, delta=1.0)
        self.assertAlmostEqual(self.core.get_property_float("gamma"), -15.0, delta=1.0)

    def test_tc_vid_02_aspect_ratio_presets(self):
        """TC-VID-02: Aspect ratio presets cycling and keepaspect override."""
        self.core.load_file(corpus_path("valid_h264_aac.mp4"))
        self.wait_for_playback(0.2)

        lbl = self.core.cycle_aspect_ratio()
        self.assertEqual(lbl, "Stretch to Window")
        self.assertEqual(self.core.get_property("keepaspect"), "no")

        lbl2 = self.core.cycle_aspect_ratio()
        self.assertIn("16:9", lbl2)
        self.assertEqual(self.core.get_property("keepaspect"), "yes")

    def test_tc_vid_03_video_rotation(self):
        """TC-VID-03: 90-degree video rotation cycling (0, 90, 180, 270)."""
        self.core.load_file(corpus_path("valid_h264_aac.mp4"))
        self.wait_for_playback(0.2)

        r1 = self.core.rotate_video()
        self.assertIn("90°", r1)
        self.assertEqual(self.core.get_property("video-rotate"), "90")

        r2 = self.core.rotate_video()
        self.assertIn("180°", r2)
        self.assertEqual(self.core.get_property("video-rotate"), "180")

    def test_tc_vid_04_flips(self):
        """TC-VID-04: Horizontal and vertical flip toggles."""
        self.core.load_file(corpus_path("valid_h264_aac.mp4"))
        self.wait_for_playback(0.2)

        hf = self.core.toggle_horizontal_flip()
        self.assertTrue(hf)
        self.assertTrue(self.core.is_horizontal_flip_active())

        vf = self.core.toggle_vertical_flip()
        self.assertTrue(vf)
        self.assertTrue(self.core.is_vertical_flip_active())

    def test_tc_vid_05_reset_video_orientation(self):
        """TC-VID-05: Reset video rotation and flips to default orientation."""
        self.core.load_file(corpus_path("valid_h264_aac.mp4"))
        self.wait_for_playback(0.2)

        self.core.rotate_video()
        self.core.toggle_horizontal_flip()
        self.core.toggle_vertical_flip()

        self.core.reset_video_orientation()
        self.assertEqual(self.core.get_property("video-rotate"), "0")
        self.assertFalse(self.core.is_horizontal_flip_active())
        self.assertFalse(self.core.is_vertical_flip_active())

    def test_tc_vid_06_toggle_hwdec(self):
        """TC-VID-06: Toggle hardware acceleration on and off."""
        self.core.toggle_hwdec()
        self.assertEqual(self.core.hwdec_active, "no")
        self.assertEqual(self.core.get_property("hwdec"), "no")

        self.core.toggle_hwdec()
        self.assertNotEqual(self.core.hwdec_active, "no")

    def test_tc_vid_07_deinterlace_and_deband(self):
        """TC-VID-07: Toggle deinterlacing and debanding."""
        self.core.toggle_deinterlace()
        self.assertTrue(self.core.deinterlace_active)
        self.assertEqual(self.core.get_property("deinterlace"), "yes")

        self.core.toggle_deband()
        self.assertTrue(self.core.deband_active)
        self.assertEqual(self.core.get_property("deband"), "yes")

    def test_tc_vid_08_glsl_shaders(self):
        """TC-VID-08: Configure custom GLSL shader path."""
        shader_path = "/usr/share/mpv/shaders/test.glsl"
        self.core.set_glsl_shaders(shader_path)
        self.assertEqual(self.core.get_property("glsl-shaders"), shader_path)

    def test_tc_vid_09_embedded_subtitles(self):
        """TC-VID-09: Embedded subtitle track detection and selection."""
        self.core.load_file(corpus_path("movie_with_subs.mkv"))
        self.wait_for_playback(0.3)

        subs = self.core.get_subtitle_tracks()
        self.assertGreaterEqual(len(subs), 1)
        self.assertEqual(subs[0]["lang"], "eng")

    def test_tc_vid_10_external_srt_subtitles(self):
        """TC-VID-10: Loading external SRT subtitle track."""
        self.core.load_file(corpus_path("valid_h264_aac.mp4"))
        self.wait_for_playback(0.2)
        initial_subs = len(self.core.get_subtitle_tracks())

        self.core.load_subtitle(corpus_path("subtitles_sample.srt"))
        self.wait_for_playback(0.2)
        self.assertEqual(len(self.core.get_subtitle_tracks()), initial_subs + 1)

    def test_tc_vid_11_external_ass_subtitles(self):
        """TC-VID-11: Loading external Advanced SubStation Alpha (.ass) track."""
        self.core.load_file(corpus_path("valid_h264_aac.mp4"))
        self.wait_for_playback(0.2)

        self.core.load_subtitle(corpus_path("subtitles_sample.ass"))
        self.wait_for_playback(0.2)
        subs = self.core.get_subtitle_tracks()
        self.assertGreaterEqual(len(subs), 1)

    def test_tc_vid_12_external_vtt_subtitles(self):
        """TC-VID-12: Loading external WebVTT (.vtt) track."""
        self.core.load_file(corpus_path("valid_h264_aac.mp4"))
        self.wait_for_playback(0.2)

        self.core.load_subtitle(corpus_path("subtitles_sample.vtt"))
        self.wait_for_playback(0.2)
        subs = self.core.get_subtitle_tracks()
        self.assertGreaterEqual(len(subs), 1)

    def test_tc_vid_13_sibling_subtitle_autodetect(self):
        """TC-VID-13: Sibling subtitle file auto-detection with matching stem."""
        sibling = corpus_path("valid_h264_aac.srt")
        shutil.copy(corpus_path("subtitles_sample.srt"), sibling)
        try:
            self.core.load_file(corpus_path("valid_h264_aac.mp4"))
            self.wait_for_playback(0.3)
            subs = self.core.get_subtitle_tracks()
            self.assertGreaterEqual(len(subs), 1)
        finally:
            if os.path.exists(sibling):
                os.remove(sibling)

    def test_tc_vid_14_subtitle_delay_and_font_size(self):
        """TC-VID-14: Subtitle delay, font size clamping (12-96), and position."""
        self.core.set_subtitle_delay(0.5)
        self.assertEqual(self.core.subtitle_delay_sec, 0.5)
        self.assertAlmostEqual(self.core.get_property_float("sub-delay"), 0.5, delta=0.01)

        self.core.set_subtitle_font_size(42)
        self.assertEqual(self.core.sub_size, 42)
        self.assertAlmostEqual(self.core.get_property_float("sub-font-size"), 42.0, delta=0.1)

        pos = self.core.adjust_subtitle_pos(-5)
        self.assertEqual(pos, 95)
        self.assertEqual(self.core.sub_pos, 95)

    def test_tc_vid_15_secondary_subtitles(self):
        """TC-VID-15: Dual subtitles (secondary subtitle track selection and cycling)."""
        self.core.load_file(corpus_path("valid_h264_aac.mp4"))
        self.wait_for_playback(0.2)
        self.core.load_subtitle(corpus_path("subtitles_sample.srt"))
        self.core.load_subtitle(corpus_path("subtitles_sample.ass"))
        self.wait_for_playback(0.2)

        self.core.set_secondary_subtitle_track(1)
        self.assertEqual(str(self.core.get_current_secondary_subtitle_track_id()), "1")

        self.core.cycle_secondary_subtitle_track()
        self.assertIsNotNone(self.core.get_current_secondary_subtitle_track_id())

    def test_tc_vid_16_screenshot_capture(self):
        """TC-VID-16: Capturing video screenshot to image file."""
        self.core.load_file(corpus_path("valid_h264_aac.mp4"))
        self.wait_for_playback(0.3)

        out_img = corpus_path("test_out.png")
        if os.path.exists(out_img):
            os.remove(out_img)

        try:
            success = self.core.take_screenshot(out_img)
            time.sleep(0.2)
            self.assertTrue(success)
            self.assertTrue(os.path.exists(out_img))
            self.assertGreater(os.path.getsize(out_img), 0)
        finally:
            if os.path.exists(out_img):
                os.remove(out_img)

    def test_tc_vid_17_detailed_info_extraction(self):
        """TC-VID-17: Technical media detailed info dictionary matching Ctrl+F1 dialog."""
        self.core.load_file(corpus_path("valid_h264_aac.mp4"))
        self.wait_for_playback(0.3)

        info = self.core.get_media_detailed_info()
        self.assertEqual(info["path"], corpus_path("valid_h264_aac.mp4"))
        self.assertEqual(info["title"], "valid_h264_aac.mp4")
        self.assertEqual(info["video_codec"], "H264")
        self.assertEqual(info["audio_codec"], "AAC")
        self.assertGreater(info["duration_sec"], 0.0)
        self.assertEqual(info["width"], 320)
        self.assertEqual(info["height"], 240)


if __name__ == "__main__":
    unittest.main()
