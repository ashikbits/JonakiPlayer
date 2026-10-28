"""
Unit tests for 10-Band Equalizer and audio filter chain generator.
"""

import unittest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from audio.equalizer import EqualizerModel, EQUALIZER_PRESETS
from audio.dsp_chain import AudioDSPChain


class TestAudioEqualizer(unittest.TestCase):
    def test_default_state(self):
        eq = EqualizerModel()
        self.assertFalse(eq.enabled)
        self.assertEqual(eq.to_filter_string(), "")

    def test_band_clipping(self):
        eq = EqualizerModel()
        eq.set_band(0, 25.0)  # Exceeds max 12.0
        self.assertEqual(eq.get_band(0), 12.0)
        eq.set_band(1, -30.0) # Exceeds min -24.0
        self.assertEqual(eq.get_band(1), -24.0)

    def test_preset_application(self):
        eq = EqualizerModel()
        self.assertFalse(eq.enabled)
        self.assertTrue(eq.apply_preset("Rock"))
        # BUG 2.1: Applying a preset must automatically enable the equalizer
        self.assertTrue(eq.enabled)
        filter_str = eq.to_filter_string()
        self.assertIn("equalizer=f=31", filter_str)
        self.assertIn("equalizer=f=16000", filter_str)

    def test_dsp_chain_neutral_bit_perfect(self):
        # BUG 3.1: Neutral DSP defaults produce empty filter string without unconditional limiter
        dsp = AudioDSPChain()
        self.assertEqual(dsp.build_filter_chain(), "")

    def test_dsp_chain(self):
        # BUG 3.3: Verify all DSP modes add their corresponding FFmpeg filters
        dsp = AudioDSPChain()
        dsp.normalizer_enabled = True
        dsp.hpf_cutoff_hz = 80
        dsp.ac3_dts_dialogue_boost = True
        dsp.harmonic_booster_enabled = True
        dsp.audio_boost_db = 6.0
        dsp.compressor_enabled = True
        dsp.channel_layout_mode = "5.1"
        chain = dsp.build_filter_chain("equalizer=f=31:width_type=o:w=1:g=3.0")

        self.assertIn("format=channel_layouts=5.1", chain)
        self.assertIn("highpass=f=80", chain)
        self.assertIn("equalizer=f=1200", chain)
        self.assertIn("equalizer=f=3500", chain)
        self.assertIn("equalizer=f=31", chain)
        self.assertIn("dynaudnorm", chain)
        self.assertIn("volume=6.0dB", chain)
        self.assertIn("acompressor", chain)
        self.assertIn("alimiter", chain)

    def test_dsp_voice_isolation_modes(self):
        dsp = AudioDSPChain()
        dsp.voice_isolation_mode = "remove_voice"
        chain_remove = dsp.build_filter_chain()
        self.assertIn("stereotools", chain_remove)

        dsp.voice_isolation_mode = "boost_voice"
        chain_boost = dsp.build_filter_chain()
        self.assertIn("equalizer=f=1800", chain_boost)

    def test_preamp_order(self):
        eq = EqualizerModel()
        eq.enabled = True
        eq.preamp_db = 4.0
        eq.set_band(0, 3.0)
        filter_str = eq.to_filter_string()
        eq_idx = filter_str.find("equalizer=f=31")
        vol_idx = filter_str.find("volume=volume=4.0dB")
        self.assertGreater(vol_idx, eq_idx)

    def test_dsp_chain_empty(self):
        dsp = AudioDSPChain()
        self.assertEqual(dsp.build_filter_chain(""), "")


if __name__ == "__main__":
    unittest.main()
