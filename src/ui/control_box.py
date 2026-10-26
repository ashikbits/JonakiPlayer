"""
Jonaki for Linux - Control Box Dialog (F6)
Quick Control Box with 5 tabs:
Audio (Equalizer & Normalizer), Video (ProcAmp), Subtitles, Playback, and Shaders.
"""

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk
from typing import Any, Callable
from audio.equalizer import FREQUENCIES, EQUALIZER_PRESETS


class ControlBoxDialog(Gtk.Window):
    def __init__(self, player_controller: Any):
        super().__init__(title="Jonaki Control Box (F6)")
        self.player = player_controller
        self.set_default_size(480, 360)
        self.set_position(Gtk.WindowPosition.CENTER)

        notebook = Gtk.Notebook()
        self.add(notebook)

        # Tab 1: Audio / Equalizer
        notebook.append_page(self._create_audio_tab(), Gtk.Label(label="Audio"))

        # Tab 2: Video Colors
        notebook.append_page(self._create_video_tab(), Gtk.Label(label="Video"))

        # Tab 3: Subtitles
        notebook.append_page(self._create_subtitle_tab(), Gtk.Label(label="Subtitles"))

        # Tab 4: Playback
        notebook.append_page(self._create_playback_tab(), Gtk.Label(label="Playback"))

        # Tab 5: Shaders
        notebook.append_page(self._create_shaders_tab(), Gtk.Label(label="Shaders"))

        self.connect("delete-event", lambda w, e: self.hide_on_delete())

    def _create_audio_tab(self) -> Gtk.Widget:
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        vbox.set_margin_start(12)
        vbox.set_margin_end(12)
        vbox.set_margin_top(12)
        vbox.set_margin_bottom(12)

        # Top Controls: Enable Equalizer & Presets Dropdown
        top_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        eq_check = Gtk.CheckButton(label="Enable Equalizer")
        eq_check.set_active(self.player.equalizer.enabled)
        eq_check.connect("toggled", self._on_eq_toggled)
        top_box.pack_start(eq_check, False, False, 0)

        preset_combo = Gtk.ComboBoxText()
        for name in EQUALIZER_PRESETS.keys():
            preset_combo.append_text(name)
        preset_combo.set_active(0)
        preset_combo.connect("changed", self._on_preset_changed)
        top_box.pack_end(preset_combo, False, False, 0)
        top_box.pack_end(Gtk.Label(label="Preset:"), False, False, 0)
        vbox.pack_start(top_box, False, False, 0)

        # 10 vertical sliders for bands
        eq_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.eq_scales = []
        for i, freq in enumerate(FREQUENCIES):
            b_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            lbl = Gtk.Label(label=f"{freq if freq < 1000 else f'{freq//1000}k'}")
            scale = Gtk.Scale(orientation=Gtk.Orientation.VERTICAL,
                              adjustment=Gtk.Adjustment(value=self.player.equalizer.get_band(i), lower=-12.0, upper=12.0, step_increment=0.5, page_increment=2.0))
            scale.set_inverted(True)
            scale.set_vexpand(True)
            scale.connect("value-changed", self._make_band_callback(i))
            self.eq_scales.append(scale)
            b_box.pack_start(scale, True, True, 0)
            b_box.pack_start(lbl, False, False, 0)
            eq_box.pack_start(b_box, True, True, 0)

        vbox.pack_start(eq_box, True, True, 0)

        # Normalizer check
        norm_check = Gtk.CheckButton(label="Enable Dynamic Audio Normalizer")
        norm_check.set_active(self.player.dsp.normalizer_enabled)
        norm_check.connect("toggled", lambda w: self.player.toggle_normalizer(w.get_active()))
        vbox.pack_start(norm_check, False, False, 0)

        return vbox

    def _make_band_callback(self, idx: int):
        def _cb(scale):
            val = scale.get_value()
            self.player.equalizer.set_band(idx, val)
            self.player.apply_audio_filters()
        return _cb

    def _on_eq_toggled(self, widget):
        self.player.equalizer.enabled = widget.get_active()
        self.player.apply_audio_filters()

    def _on_preset_changed(self, combo):
        name = combo.get_active_text()
        if name and self.player.equalizer.apply_preset(name):
            for i, scale in enumerate(self.eq_scales):
                scale.set_value(self.player.equalizer.get_band(i))
            self.player.apply_audio_filters()

    def _create_video_tab(self) -> Gtk.Widget:
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        vbox.set_margin_start(16)
        vbox.set_margin_end(16)
        vbox.set_margin_top(16)
        vbox.set_margin_bottom(16)

        self.bright_scale = self._add_slider_row(vbox, "Brightness:", -100, 100, self.player.shader_mgr.brightness, self._on_color_changed)
        self.contrast_scale = self._add_slider_row(vbox, "Contrast:", -100, 100, self.player.shader_mgr.contrast, self._on_color_changed)
        self.sat_scale = self._add_slider_row(vbox, "Saturation:", -100, 100, self.player.shader_mgr.saturation, self._on_color_changed)
        self.hue_scale = self._add_slider_row(vbox, "Hue:", -100, 100, self.player.shader_mgr.hue, self._on_color_changed)

        btn_reset = Gtk.Button(label="Reset Colors (Q)")
        btn_reset.connect("clicked", self._on_reset_colors)
        vbox.pack_start(btn_reset, False, False, 6)

        return vbox

    def _add_slider_row(self, container: Gtk.Box, label: str, min_val: float, max_val: float,
                        cur_val: float, cb: Callable) -> Gtk.Scale:
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        lbl = Gtk.Label(label=label)
        lbl.set_size_request(90, -1)
        scale = Gtk.Scale(orientation=Gtk.Orientation.HORIZONTAL,
                          adjustment=Gtk.Adjustment(value=cur_val, lower=min_val, upper=max_val, step_increment=1.0, page_increment=5.0))
        scale.connect("value-changed", cb)
        row.pack_start(lbl, False, False, 0)
        row.pack_start(scale, True, True, 0)
        container.pack_start(row, False, False, 0)
        return scale

    def _on_color_changed(self, widget):
        self.player.shader_mgr.brightness = int(self.bright_scale.get_value())
        self.player.shader_mgr.contrast = int(self.contrast_scale.get_value())
        self.player.shader_mgr.saturation = int(self.sat_scale.get_value())
        self.player.shader_mgr.hue = int(self.hue_scale.get_value())
        self.player.core.set_video_colors(
            self.player.shader_mgr.brightness,
            self.player.shader_mgr.contrast,
            self.player.shader_mgr.saturation,
            self.player.shader_mgr.hue,
            0
        )

    def _on_reset_colors(self, widget):
        self.player.shader_mgr.reset_colors()
        self.bright_scale.set_value(0)
        self.contrast_scale.set_value(0)
        self.sat_scale.set_value(0)
        self.hue_scale.set_value(0)
        self._on_color_changed(None)

    def _create_subtitle_tab(self) -> Gtk.Widget:
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        vbox.set_margin_start(16)
        vbox.set_margin_end(16)
        vbox.set_margin_top(16)
        vbox.set_margin_bottom(16)

        # Font Size
        size_scale = self._add_slider_row(vbox, "Font Size:", 16, 80, self.player.sub_mgr.font_size,
                                          lambda s: self.player.set_subtitle_size(int(s.get_value())))

        # Sync slider (-5s to +5s)
        sync_scale = self._add_slider_row(vbox, "Sync (sec):", -5.0, 5.0, self.player.sub_mgr.sync_offset_sec,
                                          lambda s: self.player.core.set_subtitle_delay(s.get_value()))

        # Translation check
        trans_check = Gtk.CheckButton(label="Enable Real-Time AI Subtitle Translation")
        trans_check.set_active(self.player.sub_mgr.translation_enabled)
        trans_check.connect("toggled", lambda w: self.player.toggle_translation(w.get_active()))
        vbox.pack_start(trans_check, False, False, 10)

        return vbox

    def _create_playback_tab(self) -> Gtk.Widget:
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        vbox.set_margin_start(16)
        vbox.set_margin_end(16)
        vbox.set_margin_top(16)
        vbox.set_margin_bottom(16)

        # Speed slider
        speed_scale = self._add_slider_row(vbox, "Speed (x):", 0.2, 3.0, self.player.core.speed,
                                           lambda s: self.player.core.set_speed(s.get_value()))

        # A-B Repeat Box
        ab_frame = Gtk.Frame(label="A-B Repeat Loop")
        ab_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        ab_box.set_margin_start(8)
        ab_box.set_margin_end(8)
        ab_box.set_margin_top(8)
        ab_box.set_margin_bottom(8)

        btn_a = Gtk.Button(label="Set A ([)")
        btn_a.connect("clicked", lambda w: self.player.set_repeat_a())
        btn_b = Gtk.Button(label="Set B (])")
        btn_b.connect("clicked", lambda w: self.player.set_repeat_b())
        btn_clear = Gtk.Button(label="Clear (\\)")
        btn_clear.connect("clicked", lambda w: self.player.core.clear_repeat())

        ab_box.pack_start(btn_a, True, True, 0)
        ab_box.pack_start(btn_b, True, True, 0)
        ab_box.pack_start(btn_clear, True, True, 0)
        ab_frame.add(ab_box)
        vbox.pack_start(ab_frame, False, False, 0)

        return vbox

    def _create_shaders_tab(self) -> Gtk.Widget:
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        vbox.set_margin_start(16)
        vbox.set_margin_end(16)
        vbox.set_margin_top(16)
        vbox.set_margin_bottom(16)

        lbl = Gtk.Label(label="Active Pixel Shaders (libplacebo / GLSL):")
        lbl.set_xalign(0.0)
        vbox.pack_start(lbl, False, False, 0)

        for shader in ["sharpen.hook", "adaptive_sharpen.hook"]:
            chk = Gtk.CheckButton(label=shader)
            chk.connect("toggled", self._make_shader_toggle_cb(shader))
            vbox.pack_start(chk, False, False, 0)

        return vbox

    def _make_shader_toggle_cb(self, shader_name: str):
        def _cb(chk):
            if chk.get_active():
                self.player.shader_mgr.enable_shader(shader_name)
            else:
                self.player.shader_mgr.disable_shader(shader_name)
            self.player.core.set_glsl_shaders(self.player.shader_mgr.get_glsl_shaders_string())
        return _cb
