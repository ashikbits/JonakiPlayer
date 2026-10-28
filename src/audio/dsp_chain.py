"""
Jonaki for Linux - Audio DSP Pipeline & Volume Booster
High-performance audio processing pipeline:
- 100% Master Volume with PreAmp Booster & Soft-Knee Limiter
- AC3/DTS Pre-Amplification & Center Dialogue Boost
- Dynamic Auto Volume Control (Normalizer)
- Harmonic Booster / Crystalizer & High-Pass Protection Filter
"""

from typing import List, Dict, Any, Optional


ENHANCEMENT_PRESETS: Dict[str, Dict[str, Any]] = {
    "Off": {
        "gain_db": 0.0,
        "compressor": False,
        "limiter": False,
        "speech_eq": False,
    },
    "Gentle / Low": {
        "gain_db": 3.0,
        "compressor": True,
        "comp_thresh": "-12dB",
        "comp_ratio": 2.0,
        "comp_attack": 20,
        "comp_release": 250,
        "comp_knee": 3.0,
        "limiter": True,
        "limit_val": 0.95,   # -0.4 dBTP ceiling
        "limit_release": 60,
        "speech_eq": False,
    },
    "Balanced / Default": {
        "gain_db": 5.0,   # Tuned PotPlayer enhancement default
        "compressor": True,
        "comp_thresh": "-10dB",
        "comp_ratio": 2.5,
        "comp_attack": 15,
        "comp_release": 200,
        "comp_knee": 2.8,
        "limiter": True,
        "limit_val": 0.92,   # -0.7 dBTP ceiling (ITU-R BS.1770 compliant)
        "limit_release": 60,
        "speech_eq": False,
    },
    "Dialogue Focus": {
        "gain_db": 5.5,
        "compressor": True,
        "comp_thresh": "-12dB",
        "comp_ratio": 3.0,
        "comp_attack": 12,
        "comp_release": 180,
        "comp_knee": 2.5,
        "limiter": True,
        "limit_val": 0.92,
        "limit_release": 60,
        "speech_eq": True,   # +2.5 dB speech formant clarity
    },
    "Dynamic / High": {
        "gain_db": 7.5,
        "compressor": True,
        "comp_thresh": "-12dB",
        "comp_ratio": 3.5,
        "comp_attack": 12,
        "comp_release": 180,
        "comp_knee": 2.5,
        "limiter": True,
        "limit_val": 0.90,   # -0.9 dBTP ceiling
        "limit_release": 50,
        "speech_eq": False,
    }
}


class AudioDSPChain:
    def __init__(self, enable_enhancement: bool = False):
        # Audio Enhancement (PotPlayer-style loudness & speech boost)
        self.enhancement_enabled: bool = enable_enhancement
        self.enhancement_preset: str = "Balanced / Default"
        self.enhancement_gain_db: float = 5.0

        # PotPlayer Audio Architecture - Clean bit-perfect defaults
        self.audio_boost_db: float = 0.0           # PreAmp boost default: 0 dB (neutral bit-perfect)
        self.ac3_dts_dialogue_boost: bool = False  # Disabled by default
        self.normalizer_enabled: bool = False      # PotPlayer Auto Volume Control default: OFF (Shift+N)
        self.harmonic_booster_enabled: bool = False
        self.compressor_enabled: bool = False
        self.voice_isolation_mode: str = "none"    # "none", "remove_voice", "boost_voice"
        self.channel_layout_mode: str = "auto"     # "auto", "stereo", "5.1", "7.1"
        self.hpf_cutoff_hz: int = 0                # Transparent by default

    def set_enhancement_enabled(self, enabled: bool) -> None:
        self.enhancement_enabled = bool(enabled)
        if self.enhancement_enabled and self.enhancement_preset == "Off":
            self.enhancement_preset = "Balanced / Default"
            cfg = ENHANCEMENT_PRESETS[self.enhancement_preset]
            self.enhancement_gain_db = cfg.get("gain_db", 5.0)

    def set_enhancement_preset(self, preset_name: str) -> bool:
        if preset_name in ENHANCEMENT_PRESETS:
            self.enhancement_preset = preset_name
            cfg = ENHANCEMENT_PRESETS[preset_name]
            if preset_name == "Off":
                self.enhancement_enabled = False
                self.enhancement_gain_db = 0.0
            else:
                self.enhancement_enabled = True
                self.enhancement_gain_db = cfg["gain_db"]
            return True
        return False

    def set_enhancement_gain(self, gain_db: float) -> None:
        self.enhancement_gain_db = max(0.0, min(15.0, float(gain_db)))

    @staticmethod
    def get_enhancement_presets() -> List[str]:
        return list(ENHANCEMENT_PRESETS.keys())

    def build_filter_chain(self, equalizer_filter_str: str = "") -> str:
        """
        Builds the unified audio filter string replicating PotPlayer's high-gain audio engine:
        Stage A: Moderate Gain (Enhancement + User PreAmp)
        Stage B: Dynamic Range Compressor (dialogue clarity, controlled crest factor)
        Stage C: True-Peak-Aware Lookahead Limiter (strict ceiling, zero clipping)
        """
        filters: List[str] = []
        cfg = ENHANCEMENT_PRESETS.get(self.enhancement_preset, ENHANCEMENT_PRESETS["Balanced / Default"])

        # 0. Channel Layout Selection / Downmixing (BUG 3.2)
        if self.channel_layout_mode in ("stereo", "5.1", "7.1"):
            filters.append(f"format=channel_layouts={self.channel_layout_mode}")

        # 1. High-Pass Filter (removes sub-audible rumble to free headroom for loudness)
        if self.hpf_cutoff_hz > 0:
            filters.append(f"highpass=f={self.hpf_cutoff_hz}")

        # 2. Dialogue / Center Channel Presence Boost
        if self.ac3_dts_dialogue_boost or (self.enhancement_enabled and cfg.get("speech_eq")):
            # Boost speech frequencies (1.2 - 1.5 kHz) for crisp, clear movie dialogue across all layouts
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
            # When combined with enhancement, use bounded maxgain (6.0) to prevent double-compression & noise pumping
            max_gain = 6.0 if self.enhancement_enabled else 12.0
            filters.append(f"dynaudnorm=f=125:g=15:m={max_gain:.1f}:r=0.9:b=1")

        # 7. Stage A — Moderate Input Gain (Unified Enhancement Gain + User PreAmp Boost)
        enh_gain = self.enhancement_gain_db if self.enhancement_enabled else 0.0
        total_gain = enh_gain + self.audio_boost_db
        if total_gain > 0.05:
            filters.append(f"volume={total_gain:.1f}dB")

        # 8. Stage B — Dynamic Range Compressor
        if self.enhancement_enabled and cfg.get("compressor"):
            filters.append(
                f"acompressor=threshold={cfg['comp_thresh']}:ratio={cfg['comp_ratio']}:"
                f"attack={cfg['comp_attack']}:release={cfg['comp_release']}:knee={cfg['comp_knee']}"
            )
        elif self.compressor_enabled:
            filters.append("acompressor=threshold=-18dB:ratio=3:attack=15:release=200")

        # 9. Stage C — True-Peak-Aware Lookahead Limiter (level=false prevents defeating ceiling)
        if (self.enhancement_enabled and cfg.get("limiter")) or total_gain > 0.05:
            lim_val = cfg.get("limit_val", 0.92) if self.enhancement_enabled else 0.95
            rel_val = cfg.get("limit_release", 60) if self.enhancement_enabled else 50
            filters.append(f"alimiter=level_in=1:level_out=1:limit={lim_val}:attack=5:release={rel_val}:asc=1:level=false")

        return ",".join(filters)
