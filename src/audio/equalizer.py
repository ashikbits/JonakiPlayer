"""
Jonaki for Linux - 10-Band Graphic Equalizer Engine
10-band equalizer engine with presets (Rock, Pop, Jazz, Classical, etc.).
"""

from typing import List, Dict, Optional


FREQUENCIES = [31, 62, 125, 250, 500, 1000, 2000, 4000, 8000, 16000]

EQUALIZER_PRESETS: Dict[str, List[float]] = {
    "Default / Flat": [0.0] * 10,
    "Pop": [1.5, 2.5, 3.0, 1.5, 0.0, -1.0, -1.0, 1.5, 2.5, 3.0],
    "Rock": [4.5, 3.5, 2.0, 0.0, -1.5, 0.0, 2.0, 3.5, 4.5, 5.0],
    "Classical": [4.0, 3.0, 2.0, 1.5, -1.0, -1.0, 0.0, 2.0, 3.0, 4.0],
    "Jazz": [3.5, 2.5, 1.0, 2.0, -1.0, -1.0, 0.0, 1.5, 2.5, 3.5],
    "Club": [0.0, 0.0, 2.5, 3.5, 3.5, 3.5, 2.0, 0.0, 0.0, 0.0],
    "Vocal": [-2.0, -1.5, 0.0, 2.5, 4.5, 4.5, 2.5, 0.0, -1.0, -2.0],
    "Bass Boost": [6.5, 5.5, 4.0, 2.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
    "Treble Boost": [0.0, 0.0, 0.0, 0.0, 0.0, 1.0, 2.5, 4.5, 6.0, 7.0],
    "Party": [5.0, 5.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 5.0, 5.0],
    "Dance": [6.0, 4.5, 2.0, 0.0, 0.0, -2.0, -3.0, -3.0, 0.0, 0.0],
    "Live": [-3.0, 0.0, 2.0, 3.0, 3.5, 3.5, 2.0, 1.0, 1.0, 1.0],
    "Techno": [5.0, 4.0, 0.0, -3.0, -2.5, 0.0, 5.0, 6.0, 6.0, 5.5]
}


class EqualizerModel:
    def __init__(self):
        self.enabled = False
        self.preamp_db: float = 0.0  # -12.0 to +12.0 dB
        self.bands: List[float] = [0.0] * 10
        self.current_preset = "Default / Flat"

    def set_band(self, index: int, gain_db: float) -> None:
        if 0 <= index < 10:
            self.bands[index] = max(-12.0, min(12.0, gain_db))

    def get_band(self, index: int) -> float:
        if 0 <= index < 10:
            return self.bands[index]
        return 0.0

    def apply_preset(self, preset_name: str) -> bool:
        if preset_name in EQUALIZER_PRESETS:
            self.bands = list(EQUALIZER_PRESETS[preset_name])
            self.current_preset = preset_name
            return True
        return False

    def reset(self) -> None:
        self.bands = [0.0] * 10
        self.preamp_db = 0.0
        self.current_preset = "Default / Flat"

    def to_filter_string(self) -> str:
        """
        Converts active equalizer settings to an FFmpeg/MPV audio filter string.
        Uses chained peaking equalizer biquads.
        """
        if not self.enabled:
            return ""

        filters = []
        if abs(self.preamp_db) > 0.01:
            filters.append(f"volume=volume={self.preamp_db}dB")

        for freq, gain in zip(FREQUENCIES, self.bands):
            if abs(gain) > 0.1:
                # Octave bandwidth is 1.0 for 10-band octave spacing
                filters.append(f"equalizer=f={freq}:width_type=o:w=1:g={gain:.1f}")

        return ",".join(filters)
