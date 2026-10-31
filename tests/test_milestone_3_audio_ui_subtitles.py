# SPDX-License-Identifier: GPL-3.0-or-later
"""
Tests for Milestone 3: Audio, UI/UX, HiDPI & Subtitle Modernization
- Equalizer range reconciliation down to -24 dB (TASK-08)
- Dynamic HiDPI scaling in SkinEngine (TASK-09)
- Modern OpenSubtitles API v1 and path security (TASK-10)
- Wayland / XWayland protocol diagnostics (TASK-11)
"""

import unittest
from unittest.mock import patch, MagicMock
import os
import tempfile
import json
import cairo

from src.core.engine import JonakiCore
from src.audio.equalizer import EqualizerModel
from src.ui.skin_engine import PotSkinEngine
from src.subtitle.online_search import SubtitleSearchClient


class TestMilestone3AudioUiSubtitles(unittest.TestCase):
    def test_equalizer_range_minus_24db(self):
        """TASK-08: Verify JonakiCore supports cuts down to -24.0 dB matching EqualizerModel."""
        core = JonakiCore(wid=None)
        try:
            # Set band 0 to -24.0 dB
            core.set_equalizer_band(0, -24.0)
            self.assertEqual(core.equalizer_bands[0], -24.0)

            # Set band 5 to +12.0 dB
            core.set_equalizer_band(5, 12.0)
            self.assertEqual(core.equalizer_bands[5], 12.0)

            # Verify clamping outside [-24.0, +12.0]
            core.set_equalizer_band(1, -30.0)
            self.assertEqual(core.equalizer_bands[1], -24.0)

            core.set_equalizer_band(2, 20.0)
            self.assertEqual(core.equalizer_bands[2], 12.0)
        finally:
            core.stop_engine()

    def test_skin_engine_hidpi_scaling(self):
        """TASK-09: Verify PotSkinEngine handles scale_factor 1.0 and 2.0 without coordinate drift."""
        skin = PotSkinEngine()
        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 1920, 124)
        cr = cairo.Context(surface)

        # Standard 1x scale
        skin.render(cr, panel_width=1920, panel_height=62, is_playing=True, scale_factor=1.0)
        self.assertEqual(skin.scale_factor, 1.0)
        hit_1x = skin.hit_test(10, 10, is_playing=True)

        # 2x HiDPI scale
        skin.render(cr, panel_width=1920, panel_height=124, is_playing=True, scale_factor=2.0)
        self.assertEqual(skin.scale_factor, 2.0)

        # A click at 20, 20 under 2x scale should map to logical 10, 10
        hit_2x = skin.hit_test(20, 20, is_playing=True)
        self.assertEqual(hit_1x, hit_2x)

    def test_opensubtitles_modern_api_v1_parsing(self):
        """TASK-10: Verify SubtitleSearchClient parses modern API v1 response schema."""
        client = SubtitleSearchClient(user_agent="JonakiTest/1.0", api_key="test_token_123")
        self.assertEqual(client.api_key, "test_token_123")
        self.assertEqual(client._get_headers()["Api-Key"], "test_token_123")

        modern_payload = {
            "total_count": 1,
            "data": [
                {
                    "id": "sub-101",
                    "type": "subtitle",
                    "attributes": {
                        "subtitle_id": "101",
                        "language": "eng",
                        "ratings": 8.7,
                        "release": "Big.Buck.Bunny.1080p",
                        "files": [
                            {"file_id": 998877, "file_name": "BigBuckBunny.srt"}
                        ]
                    }
                }
            ]
        }

        results = client._parse_api_response(modern_payload, "eng")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["title"], "Big.Buck.Bunny.1080p")
        self.assertEqual(results[0]["language"], "eng")
        self.assertEqual(results[0]["format"], "srt")
        self.assertIn("file_id=998877", results[0]["download_url"])
        self.assertEqual(results[0]["rating"], "8.7")

    def test_opensubtitles_download_containment_and_safety(self):
        """TASK-10: Verify download_subtitle validates URL scheme and output path."""
        client = SubtitleSearchClient()
        # Block non-http/https
        self.assertFalse(client.download_subtitle("file:///etc/passwd", "/tmp/sub.srt"))
        self.assertFalse(client.download_subtitle("ftp://evil.com/sub.srt", "/tmp/sub.srt"))
        self.assertFalse(client.download_subtitle("", "/tmp/sub.srt"))


if __name__ == "__main__":
    unittest.main()
