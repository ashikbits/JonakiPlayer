# SPDX-License-Identifier: GPL-3.0-or-later
"""
Jonaki for Linux - Core Playback Engine Controller (In-Process libmpv Backend)
Integrates packed libmpv directly in-process via C-FFI, delivering high-performance playback:
- Zero dropped frames at 4K / 8K 60fps with zero-copy hardware acceleration (VA-API / NVDEC / Vulkan)
- Pristine, synchronized subtitle rendering via libass (zero flickering or blinking)
- Accurate hardware metadata extraction, 10-band equalizer, AVC normalizer, and ProcAmp color balance
- Zero external subprocesses, zero Unix IPC sockets, zero detached windows
"""

import os
import sys
import time
import math
import ctypes
import json
from typing import Callable, Optional, Dict, Any, List

import gi
gi.require_version('GLib', '2.0')
from gi.repository import GLib


def set_c_numeric_locale() -> None:
    """
    Ensures LC_NUMERIC is set to 'C' in glibc so libmpv parses floating point decimals reliably.
    """
    try:
        libc = ctypes.CDLL("libc.so.6")
        libc.setlocale.argtypes = [ctypes.c_int, ctypes.c_char_p]
        libc.setlocale.restype = ctypes.c_char_p
        libc.setlocale(1, b"C")  # 1 = LC_NUMERIC
    except Exception:
        pass


def resolve_stream_url(url: str) -> tuple:
    """
    Direct playable media streams or web URLs. Handled natively via mpv's ytdl hook.
    Returns (video_url, audio_url).
    """
    return url, None


class PlaybackState:
    IDLE = "idle"
    PLAYING = "playing"
    PAUSED = "paused"
    STOPPED = "stopped"


class JonakiCore:
    """
    Core media engine backed by packed in-process libmpv.
    Embeds directly into GTK windows via native X11/XWayland Window ID (wid).
    """
    def __init__(self, wid: Optional[int] = None, ipc_socket: Optional[str] = None):
        set_c_numeric_locale()

        self.wid: Optional[int] = wid
        self.video_widget = None  # Handled via GTK DrawingArea in MainWindow
        self.state: str = PlaybackState.IDLE
        self.current_file: Optional[str] = None
        self.current_title: Optional[str] = None
        self.duration: float = 0.0
        self.position: float = 0.0
        self.volume: float = 100.0
        self.is_muted: bool = False
        self.speed: float = 1.0
        self.hwdec_active: str = "auto"
        self.video_codec: str = ""
        self.audio_codec: str = ""
        self.audio_channels: int = 2
        self.hdr_active: bool = False

        # Live media dimensions & metadata queried from engine
        self.video_width: int = 0
        self.video_height: int = 0
        self.video_fps: float = 0.0
        self.video_aspect: str = ""
        self.video_rotation_index: int = 0
        self.aspect_ratio_mode: int = 0
        self.audio_boost_db: float = 0.0
        self.normalizer_active: bool = False
        self.enhancement_active: bool = False
        self.enhancement_preset: str = "Balanced / Default"
        self.enhancement_gain_db: float = 5.0
        self.subtitle_delay_sec: float = 0.0
        self.audio_delay_sec: float = 0.0
        self.sub_pos: int = 100
        self.sub_size: int = 48
        self.deinterlace_active: bool = False
        self.deband_active: bool = False
        self.hflip_active: bool = False
        self.vflip_active: bool = False
        self.video_scale_x: float = 1.0
        self.video_scale_y: float = 1.0
        self.video_zoom: float = 1.0
        self._pending_file: Optional[tuple] = None
        self._preferred_hwdec: str = "vaapi"
        self._metadata_probed: bool = False

        # ProcAmp Color controls (-100 to 100)
        self.brightness: float = 0.0
        self.contrast: float = 0.0
        self.saturation: float = 0.0
        self.hue: float = 0.0
        self.gamma: float = 0.0

        # Equalizer 10 octave bands (-12 dB to +12 dB)
        self.equalizer_bands: List[float] = [0.0] * 10

        # A-B Repeat Loop
        self.repeat_a: Optional[float] = None
        self.repeat_b: Optional[float] = None

        # Callbacks
        self.on_time_update: Optional[Callable[[float, float], None]] = None
        self.on_state_change: Optional[Callable[[str], None]] = None
        self.on_file_end: Optional[Callable[[], None]] = None
        self.on_audio_filter_sync: Optional[Callable[[], None]] = None

        # Find and load bundled libmpv
        self.lib = self._load_bundled_libmpv()
        self._init_c_prototypes()

        self.handle: Optional[ctypes.c_void_p] = None
        self._timer_id: Optional[int] = None
        self.start_engine()

    def _load_bundled_libmpv(self) -> ctypes.CDLL:
        base_dir = os.path.dirname(__file__)
        candidates = [
            os.path.abspath(os.path.join(base_dir, "..", "..", "lib", "libmpv.so")),
            os.path.abspath(os.path.join(base_dir, "..", "..", "lib", "libmpv.so.2")),
            os.path.abspath(os.path.join(os.getcwd(), "lib", "libmpv.so")),
            "libmpv.so.2",
            "libmpv.so"
        ]
        for path in candidates:
            if os.path.exists(path) or not os.path.isabs(path):
                try:
                    return ctypes.CDLL(path)
                except Exception:
                    continue
        raise RuntimeError("Could not find or load bundled libmpv.so from project lib/ directory.")

    def _init_c_prototypes(self) -> None:
        self.lib.mpv_create.restype = ctypes.c_void_p
        self.lib.mpv_initialize.argtypes = [ctypes.c_void_p]
        self.lib.mpv_initialize.restype = ctypes.c_int
        self.lib.mpv_terminate_destroy.argtypes = [ctypes.c_void_p]
        self.lib.mpv_terminate_destroy.restype = None
        self.lib.mpv_set_option_string.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_char_p]
        self.lib.mpv_set_option_string.restype = ctypes.c_int
        self.lib.mpv_command.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_char_p)]
        self.lib.mpv_command.restype = ctypes.c_int
        self.lib.mpv_command_string.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
        self.lib.mpv_command_string.restype = ctypes.c_int
        self.lib.mpv_set_property_string.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_char_p]
        self.lib.mpv_set_property_string.restype = ctypes.c_int
        self.lib.mpv_get_property_string.restype = ctypes.c_void_p
        self.lib.mpv_get_property_string.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
        self.lib.mpv_free.argtypes = [ctypes.c_void_p]

    def start_engine(self) -> bool:
        if self.handle:
            return True
        set_c_numeric_locale()
        self.handle = self.lib.mpv_create()
        if not self.handle:
            return False

        # Configure initial hardware options before mpv_initialize
        if self.wid is not None:
            self.lib.mpv_set_option_string(self.handle, b"wid", str(self.wid).encode("utf-8"))
            self.lib.mpv_set_option_string(self.handle, b"vo", b"gpu")
        else:
            self.lib.mpv_set_option_string(self.handle, b"vo", b"null")

        # Never let mpv open detached/standalone window
        self.lib.mpv_set_option_string(self.handle, b"force-window", b"no")
        self.lib.mpv_set_option_string(self.handle, b"x11-bypass-compositor", b"no")
        has_nvidia = os.path.exists("/dev/nvidia0") or os.path.exists("/dev/nvidiactl")
        self._preferred_hwdec = "nvdec,auto-safe" if has_nvidia else "vaapi"
        hwdec_val = self._preferred_hwdec.encode("utf-8")
        self.lib.mpv_set_option_string(self.handle, b"hwdec", hwdec_val)
        self.hwdec_active = self._preferred_hwdec
        self.lib.mpv_set_option_string(self.handle, b"msg-level", b"all=warn")
        self.lib.mpv_set_option_string(self.handle, b"keep-open", b"yes")
        self.lib.mpv_set_option_string(self.handle, b"ytdl", b"yes")
        self.lib.mpv_set_option_string(self.handle, b"ytdl-format", b"bestvideo+bestaudio/best")
        self.lib.mpv_set_option_string(self.handle, b"input-default-bindings", b"no")
        self.lib.mpv_set_option_string(self.handle, b"input-vo-keyboard", b"no")
        self.lib.mpv_set_option_string(self.handle, b"cursor-autohide", b"no")
        self.lib.mpv_set_option_string(self.handle, b"input-cursor", b"no")
        self.lib.mpv_set_option_string(self.handle, b"sub-auto", b"fuzzy")
        self.lib.mpv_set_option_string(self.handle, b"sub-font-size", str(self.sub_size).encode("utf-8"))
        # Audio output routing: prefer pulse (pipewire-pulse) then pipewire then alsa
        # This guarantees proper application naming, icon, and desktop entry propagation to system soundbars
        self.lib.mpv_set_option_string(self.handle, b"ao", b"pulse,pipewire,alsa")
        self.lib.mpv_set_option_string(self.handle, b"audio-client-name", b"Jonaki")
        self.lib.mpv_set_option_string(self.handle, b"title", b"Jonaki")

        # Native hardware OSD styling (top-left notifications)
        self.lib.mpv_set_option_string(self.handle, b"osd-font", b"sans-serif")
        self.lib.mpv_set_option_string(self.handle, b"osd-font-size", b"22")
        self.lib.mpv_set_option_string(self.handle, b"osd-color", b"#FFFFFF")
        self.lib.mpv_set_option_string(self.handle, b"osd-border-color", b"#000000")
        self.lib.mpv_set_option_string(self.handle, b"osd-border-size", b"2.0")
        self.lib.mpv_set_option_string(self.handle, b"osd-align-x", b"left")
        self.lib.mpv_set_option_string(self.handle, b"osd-align-y", b"top")
        self.lib.mpv_set_option_string(self.handle, b"osd-margin-x", b"20")
        self.lib.mpv_set_option_string(self.handle, b"osd-margin-y", b"20")

        ret = self.lib.mpv_initialize(self.handle)
        if ret < 0:
            try:
                self.lib.mpv_terminate_destroy(self.handle)
            except Exception:
                pass
            self.handle = None
            return False

        # Set initial volume strictly to 100%
        self.set_property("volume", "100")

        # Start periodic tick for playback progress and metadata sync (100ms)
        if not self._timer_id:
            self._timer_id = GLib.timeout_add(100, self._query_time_tick)

        return True

    def stop_engine(self) -> None:
        if self._timer_id:
            tid = self._timer_id
            self._timer_id = None
            try:
                GLib.source_remove(tid)
            except Exception:
                pass
        if self.handle:
            h = self.handle
            self.handle = None
            try:
                self.lib.mpv_terminate_destroy(h)
            except Exception:
                pass
            self.state = PlaybackState.STOPPED

    def set_wid(self, wid: int) -> None:
        self.wid = wid
        if self.handle:
            self.set_property("wid", str(wid))
            self.set_property("vo", "gpu")
            self.set_property("cursor-autohide", "no")
            self.set_property("input-cursor", "no")
            if getattr(self, "_pending_file", None):
                pending = self._pending_file
                self._pending_file = None
                if isinstance(pending, tuple):
                    self.load_file(*pending)

    def command_args(self, *args: str) -> int:
        if not self.handle:
            return -1
        arr_type = ctypes.c_char_p * (len(args) + 1)
        c_args = arr_type(*(a.encode("utf-8") for a in args), None)
        return self.lib.mpv_command(self.handle, c_args)

    def command(self, cmd_str: str) -> int:
        if not self.handle:
            return -1
        return self.lib.mpv_command_string(self.handle, cmd_str.encode("utf-8"))

    def set_property(self, name: str, value: Any) -> int:
        if not self.handle:
            return -1
        ret = self.lib.mpv_set_property_string(self.handle, name.encode("utf-8"), str(value).encode("utf-8"))
        if ret < 0 and name == "af" and str(value):
            # Audio filter chain rejected; fallback safely to transparent filter
            self.lib.mpv_set_property_string(self.handle, b"af", b"")
        return ret

    def get_property(self, name: str) -> Optional[str]:
        if not self.handle:
            return None
        ptr = self.lib.mpv_get_property_string(self.handle, name.encode("utf-8"))
        if ptr:
            val = ctypes.string_at(ptr).decode("utf-8", errors="replace")
            self.lib.mpv_free(ptr)
            return val
        return None

    def get_property_float(self, name: str, default: float = 0.0) -> float:
        val = self.get_property(name)
        if val is not None:
            try:
                return float(val)
            except ValueError:
                pass
        return default

    def _query_time_tick(self) -> bool:
        if not self.handle:
            self._timer_id = None
            return False

        # Check demuxing abort / media loading failure
        if self.state in (PlaybackState.PLAYING, PlaybackState.PAUSED) and self.current_file:
            if self.get_property("idle-active") == "yes" and not self.get_property("path"):
                self.state = PlaybackState.STOPPED
                self.current_file = None
                self.position = 0.0
                self.duration = 0.0
                if self.on_state_change:
                    self.on_state_change(self.state)
                return True

        # Query position and duration
        pos = self.get_property_float("time-pos", 0.0)
        dur = self.get_property_float("duration", 0.0)
        self.position = pos
        self.duration = dur

        # Check track completion (eof-reached) BEFORE handling pause state.
        # Under keep-open=yes, libmpv automatically pauses when EOF is reached.
        eof = self.get_property("eof-reached")
        if eof == "yes" and self.state in (PlaybackState.PLAYING, PlaybackState.PAUSED) and self.current_file:
            self.state = PlaybackState.STOPPED
            if self.on_state_change:
                self.on_state_change(self.state)
            if self.on_file_end:
                self.on_file_end()
            return True

        # Check pause / play state
        pause_val = self.get_property("pause")
        if pause_val == "yes" and self.state == PlaybackState.PLAYING:
            self.state = PlaybackState.PAUSED
            if self.on_state_change:
                self.on_state_change(self.state)
        elif pause_val == "no" and self.state == PlaybackState.PAUSED:
            self.state = PlaybackState.PLAYING
            if self.on_state_change:
                self.on_state_change(self.state)

        # A-B Repeat loop enforcement
        if self.repeat_a is not None and self.repeat_b is not None and self.repeat_b > self.repeat_a:
            if self.position >= self.repeat_b:
                self.seek_absolute(self.repeat_a)

        # Update stream metadata once per track if playing
        if self.state == PlaybackState.PLAYING and not self._metadata_probed:
            self._update_media_metadata()
            if self.video_width > 0 or self.duration > 0:
                self._metadata_probed = True

        if self.on_time_update:
            self.on_time_update(self.position, self.duration)

        return True

    def _update_media_metadata(self) -> None:
        w = int(self.get_property_float("width", 0))
        h = int(self.get_property_float("height", 0))
        if w > 0:
            self.video_width = w
            self.video_height = h
            self.video_fps = self.get_property_float("container-fps", 0.0)
            self.video_codec = (self.get_property("video-format") or "").upper()
            self.audio_codec = (self.get_property("audio-codec-name") or "").upper()
            self.audio_channels = int(self.get_property_float("audio-params/channel-count", 2))
            aspect_flt = self.get_property_float("video-params/aspect", 0.0)
            if aspect_flt > 0:
                if abs(aspect_flt - 16 / 9) < 0.03:
                    self.video_aspect = "16:9"
                elif abs(aspect_flt - 4 / 3) < 0.03:
                    self.video_aspect = "4:3"
                elif abs(aspect_flt - 2.35) < 0.05:
                    self.video_aspect = "2.35:1"
                elif abs(aspect_flt - 1.85) < 0.05:
                    self.video_aspect = "1.85:1"
                elif abs(aspect_flt - 21 / 9) < 0.05:
                    self.video_aspect = "21:9"
                else:
                    self.video_aspect = f"{aspect_flt:.2f}:1"
            else:
                self.video_aspect = f"{w}:{h}"

    # --- Playback Operations ---

    def load_file(self, path_or_url: str, start_pts: float = 0.0, sub_file: Optional[str] = None,
                  audio_file: Optional[str] = None, user_agent: Optional[str] = None) -> None:
        if not self.wid and self.get_property("vo") != "null":
            self._pending_file = (path_or_url, start_pts, sub_file, audio_file, user_agent)
            return

        self.current_file = path_or_url
        self.current_title = os.path.basename(path_or_url) if not path_or_url.startswith("http") else path_or_url
        self.repeat_a = None
        self.repeat_b = None
        self.video_width = 0
        self.video_height = 0
        self.video_fps = 0.0
        self._metadata_probed = False

        if user_agent:
            self.set_property("user-agent", user_agent)

        self._load_file_internal(path_or_url, path_or_url, start_pts, sub_file, audio_file)

    def _load_file_internal(self, orig_path: str, resolved: str, start_pts: float,
                            sub_file: Optional[str], audio_file: Optional[str]) -> None:
        # Auto-detect sibling subtitles if none explicitly specified
        if not sub_file and not resolved.startswith(("http://", "https://", "rtsp://", "rtmp://", "mms://")):
            base, _ = os.path.splitext(resolved)
            for ext in (".srt", ".ass", ".ssa", ".vtt", ".smi", ".sub"):
                candidate = base + ext
                if os.path.exists(candidate):
                    sub_file = candidate
                    break

        opts = []
        if start_pts > 0:
            opts.append(f"start={start_pts}")
        if sub_file:
            opts.append(f"sub-file={sub_file}")
        if audio_file:
            opts.append(f"audio-file={audio_file}")

        if opts:
            self.command_args("loadfile", resolved, "replace", "-1", ",".join(opts))
        else:
            self.command_args("loadfile", resolved, "replace")

        self.set_property("pause", "no")
        self.state = PlaybackState.PLAYING
        if self.on_state_change:
            self.on_state_change(self.state)

    def play(self) -> None:
        if self.get_property("eof-reached") == "yes" or (self.duration > 0 and self.position >= self.duration - 0.2):
            self.seek_absolute(0.0)
        self.set_property("pause", "no")
        self.state = PlaybackState.PLAYING
        if self.on_state_change:
            self.on_state_change(self.state)

    def pause(self) -> None:
        self.set_property("pause", "yes")
        self.state = PlaybackState.PAUSED
        if self.on_state_change:
            self.on_state_change(self.state)

    def play_pause(self) -> None:
        if self.state == PlaybackState.PLAYING:
            self.pause()
        else:
            self.play()

    def stop(self) -> None:
        self.command("stop")
        self.state = PlaybackState.STOPPED
        self.position = 0.0
        self.duration = 0.0
        self.current_file = None
        self.current_title = None
        self.video_width = 0
        self.video_height = 0
        self.video_fps = 0.0
        self._metadata_probed = False
        if self.on_state_change:
            self.on_state_change(self.state)

    def seek_relative(self, delta_seconds: float) -> None:
        self.command(f"seek {delta_seconds} relative")

    def seek_absolute(self, target_seconds: float) -> None:
        self.command(f"seek {max(0.0, target_seconds)} absolute")

    def seek_percent(self, percent: float) -> None:
        p = max(0.0, min(100.0, percent))
        self.command(f"seek {p} absolute-percent")

    # --- Volume & Audio Controls ---

    def set_volume(self, volume: float) -> None:
        vol = max(0.0, min(100.0, volume))
        self.volume = vol
        self.set_property("volume", str(vol))

    def adjust_volume(self, delta: float) -> None:
        self.set_volume(self.volume + delta)

    def set_mute(self, muted: bool) -> None:
        self.is_muted = muted
        self.set_property("mute", "yes" if muted else "no")

    def toggle_mute(self) -> None:
        self.set_mute(not self.is_muted)

    def set_speed(self, speed: float) -> None:
        spd = max(0.1, min(16.0, speed))
        self.speed = spd
        self.set_property("speed", str(spd))

    def set_equalizer_band(self, band_index: int, gain_db: float) -> None:
        if 0 <= band_index <= 9:
            self.equalizer_bands[band_index] = max(-12.0, min(12.0, gain_db))
            self._apply_audio_filters()

    def set_audio_delay(self, delay_sec: float) -> None:
        self.audio_delay_sec = delay_sec
        self.set_property("audio-delay", str(delay_sec))

    def set_audio_boost(self, boost_db: float) -> None:
        self.audio_boost_db = max(0.0, min(24.0, boost_db))
        self._apply_audio_filters()

    def set_normalizer(self, enabled: bool) -> None:
        self.normalizer_active = enabled
        self._apply_audio_filters()

    def set_audio_enhancement(self, enabled: bool, preset: str = "Balanced / Default", gain_db: float = 5.0) -> None:
        self.enhancement_active = enabled
        self.enhancement_preset = preset
        self.enhancement_gain_db = gain_db
        if self.enhancement_active and self.enhancement_preset == "Off":
            self.enhancement_preset = "Balanced / Default"
            self.enhancement_gain_db = 5.0
        self._apply_audio_filters()

    def _apply_audio_filters(self) -> None:
        if getattr(self, "on_audio_filter_sync", None) and callable(self.on_audio_filter_sync):
            self.on_audio_filter_sync()
            return
        filters = []
        freqs = [31, 62, 125, 250, 500, 1000, 2000, 4000, 8000, 16000]
        eq_parts = []
        for i, g in enumerate(self.equalizer_bands):
            if abs(g) > 0.05:
                eq_parts.append(f"equalizer=f={freqs[i]}:width_type=o:w=1:g={g:.1f}")
        if eq_parts:
            filters.extend(eq_parts)

        if self.normalizer_active:
            m_val = 6.0 if self.enhancement_active else 12.0
            filters.append(f"dynaudnorm=f=125:g=15:m={m_val:.1f}:r=0.9:b=1")

        if self.enhancement_active and self.enhancement_preset == "Dialogue Focus":
            filters.append("equalizer=f=1200:width_type=q:w=1.2:g=2.5")

        enh_gain = self.enhancement_gain_db if self.enhancement_active else 0.0
        tot_gain = enh_gain + self.audio_boost_db
        if tot_gain > 0.05:
            filters.append(f"volume={tot_gain:.1f}dB")

        if self.enhancement_active:
            if self.enhancement_preset == "Gentle / Low":
                filters.append("acompressor=threshold=-12dB:ratio=2.0:attack=20:release=250:knee=3.0")
            elif self.enhancement_preset == "Dialogue Focus":
                filters.append("acompressor=threshold=-12dB:ratio=3.0:attack=12:release=180:knee=2.5")
            elif self.enhancement_preset == "Dynamic / High":
                filters.append("acompressor=threshold=-12dB:ratio=3.5:attack=12:release=180:knee=2.5")
            else:
                filters.append("acompressor=threshold=-10dB:ratio=2.5:attack=15:release=200:knee=2.8")

        if filters:
            lim_val = 0.90 if (self.enhancement_active and self.enhancement_preset == "Dynamic / High") else (0.92 if self.enhancement_active else 0.95)
            filters.append(f"alimiter=level_in=1:level_out=1:limit={lim_val}:attack=5:release=50:asc=1:level=false")

        af_str = ",".join(filters)
        self.set_property("af", af_str)

    # --- Video Processing & Balance (ProcAmp) ---

    def set_video_colors(self, brightness: Optional[float] = None, contrast: Optional[float] = None,
                          saturation: Optional[float] = None, hue: Optional[float] = None, gamma: Optional[float] = None) -> None:
        if brightness is not None:
            self.brightness = max(-100.0, min(100.0, brightness))
            self.set_property("brightness", str(int(self.brightness)))
        if contrast is not None:
            self.contrast = max(-100.0, min(100.0, contrast))
            self.set_property("contrast", str(int(self.contrast)))
        if saturation is not None:
            self.saturation = max(-100.0, min(100.0, saturation))
            self.set_property("saturation", str(int(self.saturation)))
        if hue is not None:
            self.hue = max(-100.0, min(100.0, hue))
            self.set_property("hue", str(int(self.hue)))
        if gamma is not None:
            self.gamma = max(-100.0, min(100.0, gamma))
            self.set_property("gamma", str(int(self.gamma)))

    def cycle_aspect_ratio(self) -> str:
        self.aspect_ratio_mode = (self.aspect_ratio_mode + 1) % 6
        modes = ["-1", "no", "16:9", "4:3", "2.35:1", "1.85:1"]
        labels = [
            "Auto (Keep Aspect Ratio)",
            "Stretch to Window",
            "16:9 Wide Preserved",
            "4:3 Standard",
            "2.35:1 CinemaScope",
            "1.85:1 VistaVision"
        ]
        if self.aspect_ratio_mode == 1:
            self.set_property("keepaspect", "no")
        else:
            self.set_property("keepaspect", "yes")
            self.set_property("video-aspect-override", modes[self.aspect_ratio_mode])
        return labels[self.aspect_ratio_mode]

    def set_aspect_ratio_mode(self, mode: str) -> None:
        modes = ["-1", "no", "16:9", "4:3", "2.35:1", "1.85:1"]
        if mode in modes:
            self.aspect_ratio_mode = modes.index(mode)
        if mode == "no":
            self.set_property("keepaspect", "no")
        else:
            self.set_property("keepaspect", "yes")
            self.set_property("video-aspect-override", mode)

    def toggle_stretch(self) -> str:
        cur = self.get_property("keepaspect")
        if cur == "no":
            self.set_property("keepaspect", "yes")
            return "Keep Aspect Ratio"
        else:
            self.set_property("keepaspect", "no")
            return "Stretch (Fill Window / Screen)"

    def rotate_video(self) -> str:
        self.video_rotation_index = (self.video_rotation_index + 1) % 4
        angles = [0, 90, 180, 270]
        labels = ["0° (Default)", "90° Clockwise", "180° Inverted", "270° Counter-Clockwise"]
        self.set_property("video-rotate", str(angles[self.video_rotation_index]))
        return labels[self.video_rotation_index]

    def toggle_horizontal_flip(self) -> bool:
        self.hflip_active = not getattr(self, "hflip_active", False)
        self.command("vf toggle hflip")
        return self.hflip_active

    def toggle_vertical_flip(self) -> bool:
        self.vflip_active = not getattr(self, "vflip_active", False)
        self.command("vf toggle vflip")
        return self.vflip_active

    def is_horizontal_flip_active(self) -> bool:
        return getattr(self, "hflip_active", False)

    def is_vertical_flip_active(self) -> bool:
        return getattr(self, "vflip_active", False)

    def reset_video_orientation(self) -> None:
        self.video_rotation_index = 0
        self.set_property("video-rotate", "0")
        if getattr(self, "hflip_active", False):
            self.command("vf toggle hflip")
            self.hflip_active = False
        if getattr(self, "vflip_active", False):
            self.command("vf toggle vflip")
            self.vflip_active = False

    def scale_video_height(self, delta: float = 0.05) -> float:
        """
        Incrementally scale video height independently.
        Clamped between 0.2 (20%) and 3.0 (300%).
        """
        if self.get_property("keepaspect") == "no":
            self.set_property("keepaspect", "yes")
        self.video_scale_y = round(max(0.2, min(3.0, self.video_scale_y + delta)), 2)
        self.set_property("video-scale-y", f"{self.video_scale_y:.2f}")
        return self.video_scale_y

    def scale_video_width(self, delta: float = 0.05) -> float:
        """
        Incrementally scale video width independently.
        Clamped between 0.2 (20%) and 3.0 (300%).
        """
        if self.get_property("keepaspect") == "no":
            self.set_property("keepaspect", "yes")
        self.video_scale_x = round(max(0.2, min(3.0, self.video_scale_x + delta)), 2)
        self.set_property("video-scale-x", f"{self.video_scale_x:.2f}")
        return self.video_scale_x

    def zoom_video(self, delta: float = 0.05) -> float:
        """
        Incrementally zoom video while preserving aspect ratio.
        Clamped between 0.2 (20%) and 4.0 (400%).
        """
        if self.get_property("keepaspect") == "no":
            self.set_property("keepaspect", "yes")
        self.video_zoom = round(max(0.2, min(4.0, self.video_zoom + delta)), 2)
        log2_zoom = math.log2(self.video_zoom)
        self.set_property("video-zoom", f"{log2_zoom:.4f}")
        return self.video_zoom

    def reset_video_dimensions(self) -> None:
        """
        Restore default video scale and zoom values (1.0x / 100%).
        """
        self.video_scale_x = 1.0
        self.video_scale_y = 1.0
        self.video_zoom = 1.0
        self.set_property("video-scale-x", "1.00")
        self.set_property("video-scale-y", "1.00")
        self.set_property("video-zoom", "0.00")
        self.set_property("keepaspect", "yes")

    def toggle_hwdec(self) -> None:
        preferred = getattr(self, "_preferred_hwdec", "auto-safe")
        if self.hwdec_active != "no":
            self.hwdec_active = "no"
        else:
            self.hwdec_active = preferred
        self.set_property("hwdec", self.hwdec_active)

    def toggle_hdr(self) -> None:
        self.hdr_active = not self.hdr_active
        self.set_property("tone-mapping", "mobius" if self.hdr_active else "auto")

    def toggle_deinterlace(self) -> None:
        self.deinterlace_active = not self.deinterlace_active
        self.set_property("deinterlace", "yes" if self.deinterlace_active else "no")

    def toggle_deband(self) -> None:
        self.deband_active = not self.deband_active
        self.set_property("deband", "yes" if self.deband_active else "no")

    def step_frame_forward(self) -> None:
        self.command("frame-step")

    def step_frame_backward(self) -> None:
        self.command("frame-back-step")

    def set_glsl_shaders(self, shaders: str) -> None:
        self.set_property("glsl-shaders", shaders)

    # --- Subtitles & Audio Tracks ---

    def load_subtitle(self, sub_path: str) -> None:
        if os.path.exists(sub_path):
            self.command_args("sub-add", sub_path, "select")

    def load_audio_track(self, track_file: str) -> None:
        if os.path.exists(track_file) or track_file.startswith("http"):
            self.command_args("audio-add", track_file, "select")

    def cycle_subtitle_track(self) -> None:
        self.command("cycle sub")

    def cycle_audio_track(self) -> None:
        self.command("cycle audio")

    def set_subtitle_visibility(self, visible: bool) -> None:
        self.set_property("sub-visibility", "yes" if visible else "no")

    def set_subtitle_delay(self, offset_sec: float) -> None:
        self.subtitle_delay_sec = offset_sec
        self.set_property("sub-delay", str(offset_sec))

    def set_subtitle_font_size(self, size_pt: int) -> None:
        self.sub_size = max(12, min(96, size_pt))
        self.set_property("sub-font-size", str(self.sub_size))

    def adjust_subtitle_pos(self, delta: int) -> int:
        self.sub_pos = max(0, min(150, self.sub_pos + delta))
        self.set_property("sub-pos", str(self.sub_pos))
        return self.sub_pos

    # --- Tracks (Audio, Subtitle, Video) & Dual Subtitles ---

    def get_track_list(self) -> List[Dict[str, Any]]:
        raw = self.get_property("track-list")
        if not raw:
            return []
        try:
            return json.loads(raw)
        except Exception:
            return []

    def get_audio_tracks(self) -> List[Dict[str, Any]]:
        return [t for t in self.get_track_list() if t.get("type") == "audio"]

    def get_subtitle_tracks(self) -> List[Dict[str, Any]]:
        return [t for t in self.get_track_list() if t.get("type") == "sub"]

    def get_video_tracks(self) -> List[Dict[str, Any]]:
        return [t for t in self.get_track_list() if t.get("type") == "video"]

    def set_audio_track(self, track_id: Any) -> None:
        self.set_property("aid", str(track_id))

    def get_current_audio_track_id(self) -> Optional[str]:
        return self.get_property("aid")

    def set_subtitle_track(self, track_id: Any) -> None:
        self.set_property("sid", str(track_id))

    def get_current_subtitle_track_id(self) -> Optional[str]:
        return self.get_property("sid")

    def set_secondary_subtitle_track(self, track_id: Any) -> None:
        self.set_property("secondary-sid", str(track_id))

    def get_current_secondary_subtitle_track_id(self) -> Optional[str]:
        return self.get_property("secondary-sid")

    def cycle_secondary_subtitle_track(self) -> None:
        self.command("cycle secondary-sid")

    def get_media_detailed_info(self) -> Dict[str, Any]:
        """
        Collects comprehensive technical playback details matching the Ctrl+F1 dialog.
        """
        w = int(self.get_property_float("width", 0)) or self.video_width
        h = int(self.get_property_float("height", 0)) or self.video_height
        fps = self.get_property_float("container-fps", 0.0) or self.video_fps
        filesize = int(self.get_property_float("file-size", 0))
        dur = self.duration or self.get_property_float("duration", 0.0)
        v_bitrate = int(self.get_property_float("video-bitrate", 0))
        a_bitrate = int(self.get_property_float("audio-bitrate", 0))

        audio_tracks = self.get_audio_tracks()
        video_tracks = self.get_video_tracks()
        has_audio = bool(audio_tracks) or bool(self.audio_codec) or bool(self.get_property("audio-codec-name"))
        has_video = bool(video_tracks) or bool(self.video_codec) or bool(self.get_property("video-format")) or (w > 0)

        sample_rate = int(self.get_property_float("audio-params/samplerate", 48000)) if has_audio else 0
        channels = (self.get_property("audio-params/channels") or "2.0 (Stereo)") if has_audio else "None"
        pix_fmt = (self.get_property("video-params/pixelformat") or "yuv420p") if has_video else "None"
        colormatrix = (self.get_property("video-params/colormatrix") or "bt.709") if has_video else "None"
        hwdec_cur = self.get_property("hwdec-current") or "no"

        return {
            "path": self.current_file or "No file loaded",
            "title": self.current_title or "No Title",
            "filesize_bytes": filesize,
            "duration_sec": dur,
            "video_codec": (self.get_property("video-format") or self.video_codec or "Unknown").upper() if has_video else "NONE",
            "width": w,
            "height": h,
            "fps": fps,
            "pixel_format": pix_fmt,
            "colormatrix": colormatrix,
            "video_bitrate": v_bitrate,
            "audio_codec": (self.get_property("audio-codec-name") or self.audio_codec or "Unknown").upper() if has_audio else "NONE",
            "audio_channels": channels,
            "sample_rate": sample_rate,
            "audio_bitrate": a_bitrate,
            "hwdec": hwdec_cur,
            "audio_delay": self.audio_delay_sec,
            "sub_delay": self.subtitle_delay_sec,
            "tracks": self.get_track_list()
        }

    # --- A-B Repeat Loop ---

    def set_repeat_point_a(self) -> float:
        self.repeat_a = self.position
        if self.repeat_b is not None and self.repeat_b <= self.repeat_a:
            self.repeat_b = None
        return self.repeat_a

    def set_repeat_point_b(self) -> Optional[float]:
        if self.repeat_a is not None and self.position > self.repeat_a:
            self.repeat_b = self.position
            return self.repeat_b
        return None

    def clear_repeat(self) -> None:
        self.repeat_a = None
        self.repeat_b = None

    def take_screenshot(self, output_path: str) -> bool:
        ret = self.command_args("screenshot-to-file", output_path, "video")
        return ret == 0
