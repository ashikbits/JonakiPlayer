"""
Jonaki for Linux - Audio DSP Pipeline & Volume Booster
High-performance audio processing pipeline:
- 100% Master Volume with PreAmp Booster & Soft-Knee Limiter
- AC3/DTS Pre-Amplification & Center Dialogue Boost
- Dynamic Auto Volume Control (Normalizer)
- Harmonic Booster / Crystalizer & High-Pass Protection Filter
"""

from typing import List


class AudioDSPChain:
    def __init__(self):
        # PotPlayer Audio Architecture - Clean bit-perfect defaults
        self.audio_boost_db: float = 0.0           # PreAmp boost default: 0 dB (neutral bit-perfect)
        self.ac3_dts_dialogue_boost: bool = False  # Disabled by default
        self.normalizer_enabled: bool = False      # PotPlayer Auto Volume Control default: OFF (Shift+N)
        self.harmonic_booster_enabled: bool = False
        self.compressor_enabled: bool = False
        self.voice_isolation_mode: str = "none"    # "none", "remove_voice", "boost_voice"
        self.channel_layout_mode: str = "stereo"   # "auto", "stereo", "5.1", "7.1"
        self.hpf_cutoff_hz: int = 0                # Transparent by default

    def build_filter_chain(self, equalizer_filter_str: str = "") -> str:
        """
        Builds the unified audio filter string replicating PotPlayer's high-gain audio engine.
        """
        filters: List[str] = []

        # 1. High-Pass Filter (removes sub-audible rumble to free headroom for loudness)
        if self.hpf_cutoff_hz > 0:
            filters.append(f"highpass=f={self.hpf_cutoff_hz}")

        # 2. Dialogue / Center Channel Presence Boost
        if self.ac3_dts_dialogue_boost:
            # Boost speech frequencies (1.2kHz) for crisp, clear movie dialogue across all layouts
            filters.append("equalizer=f=1200:width_type=q:w=1.2:g=2.5")

        # 3. User Equalizer (10 bands)
        if equalizer_filter_str:
            filters.append(equalizer_filter_str)

        # 4. Harmonic Booster / Crystalizer (Dialog 388)
        if self.harmonic_booster_enabled:
            # High-frequency presence boost around 3.5kHz to give perceived clarity and loudness
            filters.append("equalizer=f=3500:width_type=o:w=1.5:g=3.0")

        # 5. Voice isolation or extra dialogue boost
        if self.voice_isolation_mode == "remove_voice":
            filters.append("stereotools=mutel=0:muter=0:phase=1:slev=0.0")
        elif self.voice_isolation_mode == "boost_voice":
            filters.append("equalizer=f=1800:width_type=h:w=1500:g=4.5")

        # 6. Auto Volume Control / Dynamic Normalizer (Shift+N)
        if self.normalizer_enabled:
            # Look-ahead RMS dynamic leveling bringing soft sounds up to target level
            filters.append("dynaudnorm=f=125:g=15:m=12.0:r=0.9:b=1")

        # 7. PreAmp Boost (dB)
        if self.audio_boost_db > 0.0:
            filters.append(f"volume={self.audio_boost_db}dB")

        # 8. Dynamic Compressor (if enabled)
        if self.compressor_enabled:
            filters.append("acompressor=threshold=-18dB:ratio=3:attack=15:release=200")

        # 9. Master Soft-Knee Lookahead Limiter (Prevents digital clipping when boosted)
        filters.append("alimiter=limit=0.98:attack=5:release=50:asc=1")

        return ",".join(filters)
