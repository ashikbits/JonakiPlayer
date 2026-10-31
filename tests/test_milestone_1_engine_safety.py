# SPDX-License-Identifier: GPL-3.0-or-later
"""
Tests for Milestone 1: Core Engine Safety & Portability
- Thread synchronization and handle lifecycle safety (TASK-01)
- Dynamic libmpv discovery without bundled binaries (TASK-02)
- Native wakeup callback and event loop draining (TASK-03)
- Exact seeking enforcement with +exact (TASK-04)
"""

import unittest
import threading
import time
import os
import ctypes
from src.core.engine import JonakiCore, PlaybackState


class TestMilestone1EngineSafety(unittest.TestCase):
    def setUp(self):
        self.core = JonakiCore(wid=None)

    def tearDown(self):
        self.core.stop_engine()

    def test_dynamic_libmpv_discovery(self):
        """TASK-02: Verify system libmpv is discovered and loaded without bundled binaries."""
        self.assertIsNotNone(self.core.lib)
        self.assertTrue(hasattr(self.core.lib, "mpv_create"))
        self.assertTrue(hasattr(self.core.lib, "mpv_set_wakeup_callback"))
        self.assertTrue(hasattr(self.core.lib, "mpv_wait_event"))

    def test_wakeup_callback_and_event_drain(self):
        """TASK-03: Verify wakeup callback is registered and _drain_mpv_events functions safely."""
        self.assertIsNotNone(self.core._wakeup_cb_ref)
        # Manually triggering _drain_mpv_events should not crash or raise exceptions
        res = self.core._drain_mpv_events()
        self.assertFalse(res)

    def test_exact_seek_enforcement(self):
        """TASK-04: Verify seeking commands use +exact by default and support keyframe mode."""
        commands_issued = []
        original_command = self.core.command

        def intercept_command(cmd):
            commands_issued.append(cmd)
            return 0

        self.core.command = intercept_command
        try:
            # Relative exact seek (default)
            self.core.seek_relative(10.5)
            self.assertEqual(commands_issued[-1], "seek 10.5 relative+exact")

            # Relative keyframe seek
            self.core.seek_relative(10.5, exact=False)
            self.assertEqual(commands_issued[-1], "seek 10.5 relative+keyframes")

            # Absolute exact seek (default)
            self.core.seek_absolute(42.0)
            self.assertEqual(commands_issued[-1], "seek 42.0 absolute+exact")

            # Absolute keyframe seek
            self.core.seek_absolute(42.0, exact=False)
            self.assertEqual(commands_issued[-1], "seek 42.0 absolute+keyframes")

            # Percent exact seek (default)
            self.core.seek_percent(50.0)
            self.assertEqual(commands_issued[-1], "seek 50.0 absolute-percent+exact")

            # Percent keyframe seek
            self.core.seek_percent(50.0, exact=False)
            self.assertEqual(commands_issued[-1], "seek 50.0 absolute-percent+keyframes")
        finally:
            self.core.command = original_command

    def test_thread_safety_concurrency_during_teardown(self):
        """TASK-01: Verify concurrent property queries and commands during stop_engine() do not crash."""
        iterations = 50
        errors = []

        def worker_query():
            for _ in range(iterations):
                try:
                    self.core.get_property("time-pos")
                    self.core.get_property_float("volume", 100.0)
                    self.core.command("pause")
                except Exception as e:
                    errors.append(e)

        threads = [threading.Thread(target=worker_query) for _ in range(10)]
        for t in threads:
            t.start()

        time.sleep(0.01)
        # Teardown while threads are actively querying and issuing commands
        self.core.stop_engine()

        for t in threads:
            t.join()

        self.assertEqual(errors, [], f"Thread concurrency produced errors: {errors}")
        self.assertIsNone(self.core.handle)
        self.assertEqual(self.core.state, PlaybackState.STOPPED)


if __name__ == "__main__":
    unittest.main()
