# SPDX-License-Identifier: GPL-3.0-or-later
"""
Tests for Milestone 4: Real libmpv Integration & Mock Isolation (TASK-14)
Executes end-to-end against live system libmpv.so.2 without synthetic mocks.
Verifies real FFI property manipulation, filter graph application, and wakeup events.
"""

import unittest
import time
from src.core.engine import JonakiCore, PlaybackState


class TestLibmpvRealIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Initialise real JonakiCore with live system libmpv
        cls.core = JonakiCore(wid=None)

    @classmethod
    def tearDownClass(cls):
        if cls.core:
            cls.core.stop_engine()

    def test_real_handle_lifecycle_and_version(self):
        """TASK-14: Verify live libmpv handle is initialized and reports valid API version."""
        self.assertIsNotNone(self.core.handle)
        self.assertTrue(self.core._is_running)

        # Query core mpv properties
        mpv_version = self.core.get_property("mpv-version")
        self.assertIsNotNone(mpv_version)
        self.assertIn("mpv", mpv_version.lower())

    def test_real_property_roundtrip(self):
        """TASK-14: Verify get_property and set_property operate directly on real libmpv state."""
        # Volume
        self.core.set_property("volume", "78")
        vol = self.core.get_property_float("volume")
        self.assertAlmostEqual(vol, 78.0, delta=0.5)

        # Mute
        self.core.set_property("mute", "yes")
        mute_val = self.core.get_property("mute")
        self.assertEqual(mute_val, "yes")

        self.core.set_property("mute", "no")
        mute_val = self.core.get_property("mute")
        self.assertEqual(mute_val, "no")

        # Speed
        self.core.set_property("speed", "1.25")
        speed_val = self.core.get_property_float("speed")
        self.assertAlmostEqual(speed_val, 1.25, delta=0.01)

    def test_real_equalizer_filter_application(self):
        """TASK-14: Verify set_equalizer_band builds and injects valid FFmpeg audio filter into libmpv."""
        # Reset equalizer bands
        for b in range(10):
            self.core.set_equalizer_band(b, 0.0)

        # Apply -18.0 dB cut to 31 Hz band (Band 0)
        self.core.set_equalizer_band(0, -18.0)
        self.assertEqual(self.core.equalizer_bands[0], -18.0)

        # Verify libmpv accepted the filter chain without error
        af_str = self.core.get_property("af") or ""
        self.assertIn("equalizer=f=31", af_str)
        self.assertIn("-18.0", af_str)

        # Apply +6.0 dB boost to 1000 Hz band (Band 5)
        self.core.set_equalizer_band(5, 6.0)
        af_str = self.core.get_property("af") or ""
        self.assertIn("equalizer=f=1000", af_str)
        self.assertIn("6.0", af_str)

    def test_real_wakeup_event_draining(self):
        """TASK-14: Verify wakeup callback triggers and drains events non-blockingly."""
        # Changing a property enqueues an event in libmpv
        self.core.command_args("set", "pause", "yes")
        # Drain events directly
        res = self.core._drain_mpv_events()
        self.assertFalse(res)

    def test_real_engine_reinitialization(self):
        """TASK-14: Verify engine can be cleanly stopped and re-initialized with new handle."""
        temp_core = JonakiCore(wid=None)
        h1 = temp_core.handle
        self.assertIsNotNone(h1)

        temp_core.stop_engine()
        self.assertIsNone(temp_core.handle)

        temp_core.start_engine()
        h2 = temp_core.handle
        self.assertIsNotNone(h2)

        # Test command on fresh handle
        temp_core.set_property("volume", "90")
        self.assertAlmostEqual(temp_core.get_property_float("volume"), 90.0, delta=0.5)
        temp_core.stop_engine()


if __name__ == "__main__":
    unittest.main()
