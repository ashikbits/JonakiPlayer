"""
Jonaki for Linux - Media Playback Information Dialog (Ctrl+F1)
Displays comprehensive stream, container, codec, decoder, and hardware specifications.
"""

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
from gi.repository import Gtk, Gdk, Pango
from typing import Dict, Any, Optional
import os
import math


class MediaInfoDialog(Gtk.Window):
    def __init__(self, parent_window: Optional[Gtk.Window] = None):
        super().__init__(title="Playback Information (Ctrl+F1)")
        if parent_window:
            self.set_transient_for(parent_window)
        self.set_default_size(680, 520)
        self.set_position(Gtk.WindowPosition.CENTER_ON_PARENT)
        self.set_type_hint(Gdk.WindowTypeHint.DIALOG)

        # Main vertical container
        main_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        main_vbox.set_margin_start(12)
        main_vbox.set_margin_end(12)
        main_vbox.set_margin_top(12)
        main_vbox.set_margin_bottom(12)
        self.add(main_vbox)

        # Header bar
        header_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        title_label = Gtk.Label()
        title_label.set_markup("<span size='large' weight='bold' foreground='#FFD700'>Jonaki Playback Information</span>")
        header_box.pack_start(title_label, False, False, 0)
        main_vbox.pack_start(header_box, False, False, 0)

        # Scrolled Text View for formatted info
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_shadow_type(Gtk.ShadowType.ETCHED_IN)

        self.text_view = Gtk.TextView()
        self.text_view.set_editable(False)
        self.text_view.set_cursor_visible(False)
        self.text_view.set_left_margin(12)
        self.text_view.set_right_margin(12)
        self.text_view.set_top_margin(10)
        css_provider = Gtk.CssProvider()
        css_provider.load_from_data(b"textview { font-family: 'Consolas', 'Monospace', monospace; font-size: 10pt; }")
        self.text_view.get_style_context().add_provider(css_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        self.text_buffer = self.text_view.get_buffer()
        scrolled.add(self.text_view)
        main_vbox.pack_start(scrolled, True, True, 0)

        # Bottom Button Bar
        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        
        self.copy_btn = Gtk.Button(label="Copy to Clipboard")
        self.copy_btn.connect("clicked", self._on_copy_clicked)
        btn_box.pack_start(self.copy_btn, False, False, 0)

        self.status_label = Gtk.Label(label="")
        btn_box.pack_start(self.status_label, False, False, 0)

        close_btn = Gtk.Button(label="Close")
        close_btn.connect("clicked", lambda w: self.hide())
        btn_box.pack_end(close_btn, False, False, 0)

        main_vbox.pack_end(btn_box, False, False, 0)

        self.current_report_text: str = ""
        self.connect("delete-event", lambda w, e: self.hide_on_delete())
        self.connect("key-press-event", self._on_key_press)

    def _on_key_press(self, widget, event):
        if event.keyval in (Gdk.KEY_Escape, Gdk.KEY_F1):
            self.hide()
            return True
        return False

    def update_info(self, info: Dict[str, Any]) -> None:
        """
        Formats comprehensive playback report matching the Ctrl+F1 text dump.
        """
        path = info.get("path") or "No file loaded"
        filesize = info.get("filesize_bytes") or 0
        dur = float(info.get("duration_sec") or 0.0)
        w = int(info.get("width") or 0)
        h = int(info.get("height") or 0)
        fps = float(info.get("fps") or 0.0)
        v_codec = info.get("video_codec") or "None"
        pix_fmt = info.get("pixel_format") or "Unknown"
        colormatrix = info.get("colormatrix") or "Unknown"
        v_bitrate = int(info.get("video_bitrate") or 0)
        a_codec = info.get("audio_codec") or "None"
        a_channels = info.get("audio_channels") or "Unknown"
        sample_rate = int(info.get("sample_rate") or 0)
        a_bitrate = int(info.get("audio_bitrate") or 0)
        hwdec = info.get("hwdec") or "no"
        a_delay = float(info.get("audio_delay") or 0.0)
        sub_delay = float(info.get("sub_delay") or 0.0)
        tracks = info.get("tracks") or []

        # Format file size
        if filesize > 1024 * 1024 * 1024:
            size_str = f"{filesize / (1024*1024*1024):.2f} GiB ({filesize:,} bytes)"
        elif filesize > 1024 * 1024:
            size_str = f"{filesize / (1024*1024):.2f} MiB ({filesize:,} bytes)"
        elif filesize > 0:
            size_str = f"{filesize / 1024:.2f} KiB ({filesize:,} bytes)"
        else:
            size_str = "Unknown (Stream / Stdin)"

        # Format duration
        s = int(dur)
        dur_str = f"{s//3600:02d}:{(s%3600)//60:02d}:{s%60:02d}.{int((dur-s)*1000):03d}"

        # Decoder string
        if isinstance(hwdec, str) and hwdec.lower() != "no":
            dec_str = f"Hardware Acceleration Active ({hwdec.upper()})"
        else:
            dec_str = "Software Decoding (libavcodec / dav1d)"

        # Display Aspect Ratio
        if info.get("aspect"):
            dar_str = str(info["aspect"])
        elif w > 0 and h > 0:
            g = math.gcd(w, h)
            dar_str = f"{w // g}:{h // g}"
        else:
            dar_str = f"{w}:{h if h else 1}"

        lines = [
            "=" * 70,
            "                       JONAKI PLAYBACK INFORMATION",
            "=" * 70,
            "",
            "[General Information]",
            f"  File Name        : {os.path.basename(path) if path and path != 'No file loaded' else 'None'}",
            f"  Full Path        : {path}",
            f"  File Size        : {size_str}",
            f"  Duration         : {dur_str} ({dur:.2f} seconds)",
            "",
            "[Video Information]",
            f"  Video Codec      : {v_codec}",
            f"  Resolution       : {w} x {h} (Display Aspect Ratio: {dar_str})",
            f"  Frame Rate       : {fps:.3f} fps",
            f"  Pixel Format     : {pix_fmt}",
            f"  Color Matrix     : {colormatrix}",
            f"  Video Bitrate    : {f'{v_bitrate // 1000} kbps' if v_bitrate > 0 else 'Variable / Estimated'}",
            f"  Video Decoder    : {dec_str}",
            f"  Video Output     : GPU Direct Surface (EGL / X11 / Wayland zero-copy)",
            "",
            "[Audio Information]",
            f"  Audio Codec      : {a_codec}",
            f"  Channels         : {a_channels}",
            f"  Sample Rate      : {sample_rate} Hz",
            f"  Audio Bitrate    : {f'{a_bitrate // 1000} kbps' if a_bitrate > 0 else 'Variable'}",
            f"  Audio Sync Delay : {a_delay:+.2f} sec",
            f"  Audio Driver     : PulseAudio / PipeWire Low-Latency Driver",
            "",
            "[Subtitle Information]",
            f"  Subtitle Sync    : {sub_delay:+.2f} sec",
            f"  Subtitle Engine  : libass (Advanced SubStation Alpha Vector Renderer)",
        ]

        sub_tracks = [t for t in tracks if t.get("type") == "sub"]
        if sub_tracks:
            lines.append("  Embedded Tracks  :")
            for st in sub_tracks:
                tid = st.get("id", "?")
                lang = st.get("lang") or "und"
                title = st.get("title") or st.get("codec") or "Subtitle"
                sel = " [ACTIVE]" if st.get("selected") else ""
                lines.append(f"    - Track #{tid}: [{lang}] {title}{sel}")
        else:
            lines.append("  Embedded Tracks  : None (or External File)")

        lines.extend([
            "",
            "[Playback Architecture]",
            "  Player Engine    : Packed in-process libmpv2 C-FFI",
            "  UI Subsystem     : GTK3 + Cairo Native Desktop Overlay",
            "  Status           : 100% In-Process, Zero IPC subprocess overhead",
            "=" * 70
        ])

        self.current_report_text = "\n".join(lines)
        self.text_buffer.set_text(self.current_report_text)
        self.status_label.set_text("")

    def _on_copy_clicked(self, widget):
        clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        clipboard.set_text(self.current_report_text, -1)
        self.status_label.set_markup("<span foreground='#34C759'>Copied to clipboard!</span>")
