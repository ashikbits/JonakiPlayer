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
        eq.set_band(1, -30.0) # Exceeds min -12.0
        self.assertEqual(eq.get_band(1), -12.0)

    def test_preset_application(self):
        eq = EqualizerModel()
        eq.enabled = True
        self.assertTrue(eq.apply_preset("Rock"))
        filter_str = eq.to_filter_string()
        self.assertIn("equalizer=f=31", filter_str)
        self.assertIn("equalizer=f=16000", filter_str)

    def test_dsp_chain(self):
        dsp = AudioDSPChain()
        dsp.normalizer_enabled = True
        chain = dsp.build_filter_chain("equalizer=f=31:width_type=o:w=1:g=3.0")
        self.assertIn("equalizer=f=31", chain)
        self.assertIn("dynaudnorm", chain)


if __name__ == "__main__":
    unittest.main()
