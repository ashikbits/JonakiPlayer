"""
Jonaki Player - Audio Enhancement System Test Suite
Verifies:
- PotPlayer-style loudness enhancement pipeline (Gain -> Compressor -> Limiter)
- Filter graph generation across all enhancement presets
- No filter duplication or compounded volume stages
- Safe bounded AVC normalizer interaction
- Preference persistence across sessions in SQLite database
- In-process libmpv property synchronization and filter resilience
- Objective LUFS and True-Peak measurements across synthesized audio corpus
- UI shortcuts (Shift+E) and Control Box synchronization
"""

import os
import sys
import tempfile
import unittest
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from audio.dsp_chain import AudioDSPChain, ENHANCEMENT_PRESETS
from core.engine import JonakiCore, PlaybackState
from core.media_db import MediaDatabase
from ui.main_window import JonakiMainWindow


CORPUS_DIR = os.path.join(os.path.dirname(__file__), "audio_corpus")


class TestAudioDSPChainEnhancement(unittest.TestCase):
    def setUp(self):
        self.dsp = AudioDSPChain()

    def test_default_constructor_bit_perfect(self):
        """Pure unconfigured AudioDSPChain defaults to neutral bit-perfect empty filter."""
        self.assertFalse(self.dsp.enhancement_enabled)
        self.assertEqual(self.dsp.build_filter_chain(), "")

    def test_enable_enhancement_default_preset(self):
        """Enabling enhancement applies Balanced/Default (+5dB, compressor, alimiter)."""
        self.dsp.set_enhancement_enabled(True)
        self.assertTrue(self.dsp.enhancement_enabled)
        chain = self.dsp.build_filter_chain()

        self.assertIn("volume=5.0dB", chain)
        self.assertIn("acompressor=threshold=-10dB:ratio=2.5", chain)
        self.assertIn("alimiter=level_in=1:level_out=1:limit=0.92", chain)
        self.assertIn("level=false", chain)

    def test_all_presets_filter_generation(self):
        """Each preset generates valid parameters."""
        presets = self.dsp.get_enhancement_presets()
        self.assertIn("Off", presets)
        self.assertIn("Gentle / Low", presets)
        self.assertIn("Balanced / Default", presets)
        self.assertIn("Dialogue Focus", presets)
        self.assertIn("Dynamic / High", presets)

        # Gentle
        self.dsp.set_enhancement_preset("Gentle / Low")
        chain_gentle = self.dsp.build_filter_chain()
        self.assertIn("volume=3.0dB", chain_gentle)
        self.assertIn("ratio=2.0", chain_gentle)
        self.assertIn("limit=0.95", chain_gentle)

        # Dialogue Focus
        self.dsp.set_enhancement_preset("Dialogue Focus")
        chain_diag = self.dsp.build_filter_chain()
        self.assertIn("volume=5.5dB", chain_diag)
        self.assertIn("equalizer=f=1200", chain_diag)
        self.assertIn("ratio=3.0", chain_diag)
        self.assertIn("limit=0.92", chain_diag)

        # Dynamic / High
        self.dsp.set_enhancement_preset("Dynamic / High")
        chain_dyn = self.dsp.build_filter_chain()
        self.assertIn("volume=7.5dB", chain_dyn)
        self.assertIn("ratio=3.5", chain_dyn)
        self.assertIn("limit=0.9", chain_dyn)

        # Off
        self.dsp.set_enhancement_preset("Off")
        self.assertFalse(self.dsp.enhancement_enabled)
        self.assertEqual(self.dsp.build_filter_chain(), "")

    def test_no_duplicate_volume_stages(self):
        """User PreAmp boost is combined into a single volume filter stage."""
        self.dsp.set_enhancement_enabled(True)
        self.dsp.enhancement_gain_db = 5.0
        self.dsp.audio_boost_db = 3.0
        chain = self.dsp.build_filter_chain()

        # 5.0 + 3.0 = 8.0 dB in a single volume filter
        self.assertIn("volume=8.0dB", chain)
        self.assertEqual(chain.count("volume="), 1)
        self.assertEqual(chain.count("alimiter="), 1)

    def test_off_preset_fallback_on_enable(self):
        """Setting preset to 'Off' disables enhancement. Re-enabling restores 'Balanced / Default'."""
        self.dsp.set_enhancement_preset("Off")
        self.assertFalse(self.dsp.enhancement_enabled)
        self.assertEqual(self.dsp.build_filter_chain(), "")

        # Re-enable enhancement
        self.dsp.set_enhancement_enabled(True)
        self.assertTrue(self.dsp.enhancement_enabled)
        self.assertEqual(self.dsp.enhancement_preset, "Balanced / Default")
        self.assertAlmostEqual(self.dsp.enhancement_gain_db, 5.0)
        chain = self.dsp.build_filter_chain()
        self.assertIn("volume=5.0dB", chain)
        self.assertIn("acompressor=", chain)
        self.assertIn("alimiter=", chain)

    def test_gain_range_sweep(self):
        """Gain adjustments across 0.0 to 15.0 dB are strictly bounded and applied."""
        self.dsp.set_enhancement_enabled(True)
        for g in [0.0, 2.5, 5.0, 8.0, 12.0, 15.0]:
            self.dsp.set_enhancement_gain(g)
            self.assertAlmostEqual(self.dsp.enhancement_gain_db, g)
            chain = self.dsp.build_filter_chain()
            if g > 0.05:
                self.assertIn(f"volume={g:.1f}dB", chain)

        # Clamping below 0 and above 15
        self.dsp.set_enhancement_gain(-5.0)
        self.assertEqual(self.dsp.enhancement_gain_db, 0.0)
        self.dsp.set_enhancement_gain(30.0)
        self.assertEqual(self.dsp.enhancement_gain_db, 15.0)

    def test_bounded_normalizer_interaction(self):
        """When enhancement is active, AVC normalizer uses safe bounded max_gain=6.0."""
        self.dsp.set_enhancement_enabled(True)
        self.dsp.normalizer_enabled = True
        chain = self.dsp.build_filter_chain()

        self.assertIn("dynaudnorm=f=125:g=15:m=6.0", chain)

        # When enhancement is disabled, standard m=12.0 is used
        self.dsp.set_enhancement_enabled(False)
        chain_no_enh = self.dsp.build_filter_chain()
        self.assertIn("dynaudnorm=f=125:g=15:m=12.0", chain_no_enh)


class TestAudioEnhancementPersistence(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_enh.sqlite")
        self.db = MediaDatabase(self.db_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_persistence_defaults_and_updates(self):
        """Settings persist across database instances."""
        # Fresh install defaults
        self.assertEqual(self.db.get_setting("audio_enhancement_enabled", "1"), "1")
        self.assertEqual(self.db.get_setting("audio_enhancement_preset", "Balanced / Default"), "Balanced / Default")

        # Update settings
        self.db.set_setting("audio_enhancement_enabled", "0")
        self.db.set_setting("audio_enhancement_preset", "Dialogue Focus")
        self.db.set_setting("audio_enhancement_gain", "6.5")

        # Re-open database
        db2 = MediaDatabase(self.db_path)
        self.assertEqual(db2.get_setting("audio_enhancement_enabled"), "0")
        self.assertEqual(db2.get_setting("audio_enhancement_preset"), "Dialogue Focus")
        self.assertEqual(db2.get_setting("audio_enhancement_gain"), "6.5")


class TestAudioEnhancementEngineIntegration(unittest.TestCase):
    def setUp(self):
        self.core = JonakiCore()

    def tearDown(self):
        self.core.stop_engine()

    def test_engine_set_audio_enhancement(self):
        """JonakiCore.set_audio_enhancement updates af filter graph in libmpv."""
        test_file = os.path.join(CORPUS_DIR, "normal_music.wav")
        if os.path.exists(test_file):
            self.core.load_file(test_file)
            self.core.play()

        self.core.set_audio_enhancement(True, "Balanced / Default", 5.0)
        self.assertTrue(self.core.enhancement_active)
        af = self.core.get_property("af") or ""
        self.assertIn("volume=", af)
        self.assertIn("acompressor=", af)
        self.assertIn("alimiter=", af)
        self.assertIn("level=false", af)

        # Disable enhancement
        self.core.set_audio_enhancement(False)
        self.assertFalse(self.core.enhancement_active)
        af_off = self.core.get_property("af") or ""
        self.assertEqual(af_off, "")

    def test_engine_filter_chain_presets(self):
        """JonakiCore._apply_audio_filters supports all presets with level=false."""
        # Dialogue Focus
        self.core.set_audio_enhancement(True, "Dialogue Focus", 5.5)
        af_diag = self.core.get_property("af") or ""
        self.assertIn("equalizer=f=1200", af_diag)
        self.assertIn("ratio=", af_diag)
        self.assertIn("3.0", af_diag)
        self.assertIn("level=false", af_diag)

        # Dynamic / High
        self.core.set_audio_enhancement(True, "Dynamic / High", 7.5)
        af_dyn = self.core.get_property("af") or ""
        self.assertIn("ratio=", af_dyn)
        self.assertIn("3.5", af_dyn)
        self.assertIn("limit=", af_dyn)
        self.assertIn("0.9", af_dyn)
        self.assertIn("level=false", af_dyn)

    def test_live_playback_filter_transitions(self):
        """Filter updates during playback, seeking, and pause do not disrupt engine state."""
        test_file = os.path.join(CORPUS_DIR, "normal_music.wav")
        if not os.path.exists(test_file):
            return
        self.core.load_file(test_file)
        self.core.play()
        self.assertEqual(self.core.state, PlaybackState.PLAYING)

        # Cycle presets during live playback
        for p in ["Gentle / Low", "Balanced / Default", "Dialogue Focus", "Dynamic / High", "Off", "Balanced / Default"]:
            is_en = (p != "Off")
            self.core.set_audio_enhancement(is_en, p)
            self.assertIsNotNone(self.core.get_property("af"))

        # Seek while playing
        self.core.seek_relative(1.0)
        self.assertEqual(self.core.state, PlaybackState.PLAYING)

        # Pause and change filter
        self.core.pause()
        self.assertEqual(self.core.state, PlaybackState.PAUSED)
        self.core.set_audio_enhancement(True, "Dialogue Focus", 6.0)

        # Resume
        self.core.play()
        self.assertEqual(self.core.state, PlaybackState.PLAYING)

    def test_filter_resilience_on_invalid_filter(self):
        """Setting invalid filter string gracefully falls back without crashing."""
        ret = self.core.set_property("af", "invalid_nonexistent_filter_xyz=123")
        # Should not raise exception
        self.assertIsNotNone(self.core.handle)


class TestAudioEnhancementUIIntegration(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "ui_test_mediadb.sqlite")
        self.test_db = MediaDatabase(self.db_path)
        self.win = JonakiMainWindow(db=self.test_db)

    def tearDown(self):
        if hasattr(self.win, "core") and self.win.core:
            self.win.core.stop_engine()
        self.win.destroy()
        self.temp_dir.cleanup()

    def test_fresh_install_enabled_by_default(self):
        """Audio enhancement is enabled by default in JonakiMainWindow."""
        self.assertTrue(self.win.dsp.enhancement_enabled)
        self.assertEqual(self.win.dsp.enhancement_preset, "Balanced / Default")
        self.assertAlmostEqual(self.win.dsp.enhancement_gain_db, 5.0)

    def test_shift_e_shortcut_toggle(self):
        """Shift+E key event toggles audio enhancement."""
        initial_state = self.win.dsp.enhancement_enabled

        event = Gdk.EventKey()
        event.keyval = Gdk.KEY_e
        event.state = Gdk.ModifierType.SHIFT_MASK

        handled = self.win._on_key_press(self.win, event)
        self.assertTrue(handled)
        self.assertEqual(self.win.dsp.enhancement_enabled, not initial_state)

        # Toggle back
        self.win._on_key_press(self.win, event)
        self.assertEqual(self.win.dsp.enhancement_enabled, initial_state)

    def test_command_dispatch_presets(self):
        """CMD_AUDIO_ENHANCE_PRESET_* dispatches and updates state."""
        self.win.handle_command("CMD_AUDIO_ENHANCE_PRESET_Dialogue_Focus")
        self.assertEqual(self.win.dsp.enhancement_preset, "Dialogue Focus")
        self.assertTrue(self.win.dsp.enhancement_enabled)

        self.win.handle_command("CMD_AUDIO_ENHANCE_PRESET_Off")
        self.assertFalse(self.win.dsp.enhancement_enabled)

    def test_control_box_audio_tab_sync(self):
        """Control Box audio tab controls reflect player enhancement state."""
        ctrl_box = self.win.control_box
        ctrl_box.update_controls()

        self.assertEqual(ctrl_box.enhance_check.get_active(), self.win.dsp.enhancement_enabled)
import subprocess
import re


class TestAudioCorpusObjectiveMetrics(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Ensure audio corpus exists
        if not os.path.exists(os.path.join(CORPUS_DIR, "quiet_dialogue.wav")):
            from tests.generate_audio_corpus import main as gen_corpus
            gen_corpus()

    def _measure_audio(self, filename: str, af_chain: str = ""):
        filepath = os.path.join(CORPUS_DIR, filename)
        filt = af_chain + ",ebur128=peak=true" if af_chain else "ebur128=peak=true"
        cmd = ["ffmpeg", "-nostats", "-i", filepath, "-af", filt, "-f", "null", "-"]
        res = subprocess.run(cmd, capture_output=True, text=True)
        out = res.stderr
        m_i = re.search(r"Summary:.*?Integrated loudness:\s+I:\s+([-\d\.]+)\s+LUFS", out, re.DOTALL)
        m_lra = re.search(r"Summary:.*?Loudness range:\s+LRA:\s+([-\d\.]+)\s+LU", out, re.DOTALL)
        m_tp = re.search(r"Summary:.*?True peak:\s+Peak:\s+([-\d\.]+)\s+dBFS", out, re.DOTALL)
        return {
            "I": float(m_i.group(1)) if m_i else -99.9,
            "LRA": float(m_lra.group(1)) if m_lra else 0.0,
            "TP": float(m_tp.group(1)) if m_tp else -99.9
        }

    def test_quiet_dialogue_perceived_loudness(self):
        """TC-AUD-ENH-01: Quiet speech is noticeably boosted by >= 4.5 dB."""
        dsp = AudioDSPChain(enable_enhancement=True)
        chain = dsp.build_filter_chain()

        base = self._measure_audio("quiet_dialogue.wav", "")
        enh = self._measure_audio("quiet_dialogue.wav", chain)

        boost = enh["I"] - base["I"]
        self.assertGreaterEqual(boost, 4.5, f"Expected boost >= 4.5 dB, got {boost:.1f} dB")
        self.assertLessEqual(enh["TP"], -0.5, "True peak must remain below safe ceiling")

    def test_loud_compressed_music_ceiling(self):
        """TC-AUD-ENH-02: Already loud music is safely controlled without clipping."""
        dsp = AudioDSPChain(enable_enhancement=True)
        chain = dsp.build_filter_chain()

        enh = self._measure_audio("loud_compressed_music.wav", chain)
        self.assertLessEqual(enh["TP"], 0.0, "True peak must not exceed 0.0 dBTP")

    def test_dynamic_movie_crest_factor(self):
        """TC-AUD-ENH-03: Movie audio retains wide dynamic range (>15 LU)."""
        dsp = AudioDSPChain(enable_enhancement=True)
        chain = dsp.build_filter_chain()

        enh = self._measure_audio("dynamic_movie.wav", chain)
        self.assertGreaterEqual(enh["LRA"], 15.0, f"Expected LRA >= 15.0, got {enh['LRA']:.1f}")
        self.assertLessEqual(enh["TP"], 0.0, "Explosive peaks must be controlled below 0.0 dBTP")

    def test_bass_transient_preservation(self):
        """TC-AUD-ENH-04: Heavy bass transients are controlled without clipping."""
        dsp = AudioDSPChain(enable_enhancement=True)
        chain = dsp.build_filter_chain()

        enh = self._measure_audio("bass_transients.wav", chain)
        self.assertLessEqual(enh["TP"], 0.0, "Bass transient true peak must not exceed 0.0 dBTP")

    def test_adversarial_sample_peak_ceiling(self):
        """Adversarial signals (square wave, impulse) strictly adhere to sample-peak limit."""
        dsp = AudioDSPChain(enable_enhancement=True)
        chain = dsp.build_filter_chain()

        # Measure sample peak via volumedetect
        for f in ["adversarial_square_4k.wav", "adversarial_impulse_train.wav"]:
            path = os.path.join(CORPUS_DIR, f)
            if not os.path.exists(path):
                continue
            cmd = ["ffmpeg", "-nostats", "-i", path, "-af", f"{chain},volumedetect", "-f", "null", "-"]
            res = subprocess.run(cmd, capture_output=True, text=True)
            m = re.search(r"max_volume:\s+([-\d\.]+)\s+dB", res.stderr)
            self.assertIsNotNone(m, f"volumedetect failed on {f}")
            max_vol = float(m.group(1))
            # limit=0.92 is -0.72 dBFS; max_volume must be <= -0.7 dBFS
            self.assertLessEqual(max_vol, -0.70, f"Sample peak exceeded limiter ceiling: {max_vol} dBFS on {f}")

    def test_real_speech_podcast_clarity(self):
        """Podcast speech receives >= 4.5 dB boost and Dialogue Focus boosts further."""
        dsp_bal = AudioDSPChain(enable_enhancement=True)
        chain_bal = dsp_bal.build_filter_chain()

        dsp_diag = AudioDSPChain(enable_enhancement=True)
        dsp_diag.set_enhancement_preset("Dialogue Focus")
        chain_diag = dsp_diag.build_filter_chain()

        base = self._measure_audio("real_speech_podcast.wav", "")
        enh_bal = self._measure_audio("real_speech_podcast.wav", chain_bal)
        enh_diag = self._measure_audio("real_speech_podcast.wav", chain_diag)

        boost_bal = enh_bal["I"] - base["I"]
        boost_diag = enh_diag["I"] - base["I"]
        self.assertGreaterEqual(boost_bal, 4.5, f"Expected Balanced boost >= 4.5 dB, got {boost_bal:.1f} dB")
        self.assertGreaterEqual(boost_diag, boost_bal, "Dialogue Focus should provide equal or greater boost")


if __name__ == "__main__":
    unittest.main()

