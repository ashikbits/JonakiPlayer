"""
Jonaki for Linux - OSD & Tab Technical Information Overlay
Renders the technical statistics HUD and transient OSD notifications.
"""

import time
from typing import Dict, Any, Optional
import cairo


class OSDOverlay:
    def __init__(self):
        self.show_tech_info: bool = False
        self.message: str = ""
        self.message_expire_time: float = 0.0
        self.translated_sub: str = ""
        self.translated_sub_expire: float = 0.0

    def show_osd(self, text: str, duration_sec: float = 2.0) -> None:
        self.message = text
        self.message_expire_time = time.time() + duration_sec

    def set_translated_sub(self, text: str, duration_sec: float = 3.5) -> None:
        self.translated_sub = text
        self.translated_sub_expire = time.time() + duration_sec

    def toggle_tech_info(self) -> bool:
        self.show_tech_info = not self.show_tech_info
        return self.show_tech_info

    def render(self, cr: cairo.Context, window_width: int, window_height: int,
               media_info: Dict[str, Any], position_sec: float, duration_sec: float,
               skip_transient_osd: bool = False) -> None:
        now = time.time()

        # 1. Transient OSD Notification (Top Left)
        if not skip_transient_osd and self.message and now < self.message_expire_time:
            cr.save()
            cr.select_font_face("Segoe UI", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
            cr.set_font_size(18.0)

            # Draw text shadow / outline
            cr.set_source_rgba(0.0, 0.0, 0.0, 0.8)
            cr.move_to(25, 41)
            cr.show_text(self.message)

            # Draw white text
            cr.set_source_rgb(1.0, 1.0, 1.0)
            cr.move_to(24, 40)
            cr.show_text(self.message)
            cr.restore()

        # 2. Translated AI Subtitle (Bottom Center, positioned above skin bar)
        if self.translated_sub and now < self.translated_sub_expire:
            cr.save()
            cr.select_font_face("Segoe UI", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
            cr.set_font_size(24.0)
            sub_lines = [l for l in self.translated_sub.split("\n") if l.strip()]
            line_height = 32.0
            start_y = max(40, window_height - 90 - int((len(sub_lines) - 1) * line_height))

            for i, line_text in enumerate(sub_lines):
                extents = cr.text_extents(line_text)
                x = max(10, (window_width - extents.width) / 2)
                y = start_y + (i * line_height)

                # High-contrast outline / shadow
                cr.set_source_rgba(0.0, 0.0, 0.0, 0.9)
                for dx, dy in [(-2, 0), (2, 0), (0, -2), (0, 2), (-2, -2), (2, 2)]:
                    cr.move_to(x + dx, y + dy)
                    cr.show_text(line_text)

                # Vibrant PotPlayer gold subtitle text
                cr.set_source_rgb(1.0, 0.88, 0.25)
                cr.move_to(x, y)
                cr.show_text(line_text)

            cr.restore()

        # 3. Tab Technical Playback Info HUD
        if self.show_tech_info:
            self._render_tech_hud(cr, window_width, window_height, media_info, position_sec, duration_sec)

    def _render_tech_hud(self, cr: cairo.Context, width: int, height: int,
                         info: Dict[str, Any], pos: float, dur: float) -> None:
        cr.save()

        # Semi-transparent dark background card
        card_w = min(560, width - 40)
        card_h = 320
        cr.rectangle(20, 20, card_w, card_h)
        cr.clip()

        cr.set_source_rgba(0.08, 0.08, 0.10, 0.85)
        cr.rectangle(20, 20, card_w, card_h)
        cr.fill()

        # Border
        cr.set_source_rgba(0.3, 0.3, 0.35, 0.8)
        cr.set_line_width(1.0)
        cr.rectangle(20.5, 20.5, card_w - 1, card_h - 1)
        cr.stroke()

        # Header Title
        cr.select_font_face("Segoe UI", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
        cr.set_font_size(13.0)
        cr.set_source_rgb(0.95, 0.75, 0.20)  # Jonaki Gold accent
        cr.move_to(35, 45)
        cr.show_text("Jonaki Playback Information (TAB)")

        # Divider line
        cr.set_source_rgba(0.35, 0.35, 0.4, 0.8)
        cr.move_to(35, 55.5)
        cr.line_to(20 + card_w - 15, 55.5)
        cr.stroke()

        # Details list
        cr.select_font_face("Consolas", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
        cr.set_font_size(11.0)

        file_str = str(info.get('file_path') or 'No file loaded')
        if len(file_str) > 55:
            file_str = "..." + file_str[-52:]

        fps_val = float(info.get('fps') or 0.0)
        hwdec_val = info.get("hwdec")
        dec_str = f"HW: {hwdec_val.upper()}" if isinstance(hwdec_val, str) and hwdec_val.lower() != 'no' else 'SW: FFmpeg'

        lines = [
            f"File:         {file_str}",
            f"Playback:     {self._format_hms(pos)} / {self._format_hms(dur)} ({(pos/dur*100) if dur > 0 else 0:.1f}%)",
            f"Video Codec:  {info.get('video_codec', 'None')} ({info.get('pixel_format', 'YUV420P')})",
            f"Resolution:   {info.get('width', 1920)} x {info.get('height', 1080)} (Aspect: {info.get('aspect', '16:9')})",
            f"FPS:          {fps_val:.2f} fps",
            f"Decoder:      [{dec_str}]",
            f"Audio Codec:  {info.get('audio_codec', 'AAC')} ({info.get('audio_channels', 2)} Channels)",
            f"Sample Rate:  {info.get('sample_rate', 48000)} Hz",
            f"Output Sink:  PipeWire / PulseAudio Low-Latency Sink",
            f"Render Stack: Linux Wayland/X11 EGL + libplacebo GLSL",
            f"Frames Drop:  {info.get('dropped_frames', 0)} dropped",
        ]

        y = 78
        for line in lines:
            cr.set_source_rgb(0.85, 0.85, 0.90)
            cr.move_to(35, y)
            cr.show_text(line)
            y += 21

        cr.restore()

    def _format_hms(self, sec: float) -> str:
        s = int(max(0.0, sec))
        hrs = s // 3600
        mins = (s % 3600) // 60
        secs = s % 60
        return f"{hrs:02d}:{mins:02d}:{secs:02d}"
