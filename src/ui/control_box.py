"""
Jonaki for Linux - Control Box Dialog (F6)
Quick Control Box with 5 tabs:
Audio (Equalizer & Normalizer), Video (ProcAmp), Subtitles, Playback, and Shaders.
"""

import os
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk
from typing import Any, Callable
from audio.equalizer import FREQUENCIES, EQUALIZER_PRESETS


class ControlBoxDialog(Gtk.Window):
    def __init__(self, player_controller: Any):
        super().__init__(title="Jonaki Control Box (F6)")
        self.player = player_controller
        if isinstance(player_controller, Gtk.Window):
            self.set_transient_for(player_controller)
        self.set_default_size(480, 360)
        self.set_position(Gtk.WindowPosition.CENTER_ON_PARENT)

        self._updating_controls: bool = False
        self.notebook = Gtk.Notebook()
        self.add(self.notebook)

        # Tab 0: Audio / Equalizer
        self.notebook.append_page(self._create_audio_tab(), Gtk.Label(label="Audio"))

        # Tab 1: Video Colors
        self.notebook.append_page(self._create_video_tab(), Gtk.Label(label="Video"))

        # Tab 2: Subtitles
        self.notebook.append_page(self._create_subtitle_tab(), Gtk.Label(label="Subtitles"))

        # Tab 3: Playback
        self.notebook.append_page(self._create_playback_tab(), Gtk.Label(label="Playback"))

        # Tab 4: Shaders
        self.notebook.append_page(self._create_shaders_tab(), Gtk.Label(label="Shaders"))

        self.connect("delete-event", lambda w, e: self.hide_on_delete())
        self.connect("show", lambda w: self.update_controls())
        self.connect("key-press-event", self._on_key_press)

    def _on_key_press(self, widget, event):
        if event.keyval in (Gdk.KEY_Escape, Gdk.KEY_F5, Gdk.KEY_F6):
            self.hide()
            return True
        if event.keyval == Gdk.KEY_F7:
            if self.notebook.get_current_page() == 0:
                self.hide()
            else:
                self.select_tab(0)
            return True
        return False

    def select_tab(self, index: int) -> None:
        if 0 <= index < self.notebook.get_n_pages():
            self.notebook.set_current_page(index)

    def update_controls(self) -> None:
        """
        Synchronizes all dialog sliders, checkbuttons, and combo states with current engine values.
        """
        self._updating_controls = True
        try:
            # Audio tab
            if hasattr(self, "eq_check") and hasattr(self.player, "equalizer"):
                self.eq_check.set_active(self.player.equalizer.enabled)
            if hasattr(self, "preset_combo") and hasattr(self.player, "equalizer"):
                cur_preset = getattr(self.player.equalizer, "current_preset", None)
                if cur_preset:
                    for idx, name in enumerate(EQUALIZER_PRESETS.keys()):
                        if name == cur_preset:
                            self.preset_combo.set_active(idx)
                            break
            if hasattr(self, "eq_scales") and hasattr(self.player, "equalizer"):
                for i, scale in enumerate(self.eq_scales):
                    scale.set_value(self.player.equalizer.get_band(i))
            if hasattr(self, "norm_check") and hasattr(self.player, "dsp"):
                self.norm_check.set_active(self.player.dsp.normalizer_enabled)
            if hasattr(self, "enhance_check") and hasattr(self.player, "dsp"):
                self.enhance_check.set_active(self.player.dsp.enhancement_enabled)
            if hasattr(self, "enhance_combo") and hasattr(self.player, "dsp"):
                presets = ["Gentle / Low", "Balanced / Default", "Dialogue Focus", "Dynamic / High"]
                matched = False
                for idx, p in enumerate(presets):
                    if p in self.player.dsp.enhancement_preset:
                        self.enhance_combo.set_active(idx)
                        matched = True
                        break
                if not matched:
                    self.enhance_combo.set_active(1)
            if hasattr(self, "enhance_gain_scale") and hasattr(self.player, "dsp"):
                self.enhance_gain_scale.set_value(self.player.dsp.enhancement_gain_db)

            # Video tab
            if hasattr(self.player, "shader_mgr"):
                if hasattr(self, "bright_scale"):
                    self.bright_scale.set_value(self.player.shader_mgr.brightness)
                if hasattr(self, "contrast_scale"):
                    self.contrast_scale.set_value(self.player.shader_mgr.contrast)
                if hasattr(self, "sat_scale"):
                    self.sat_scale.set_value(self.player.shader_mgr.saturation)
                if hasattr(self, "hue_scale"):
                    self.hue_scale.set_value(self.player.shader_mgr.hue)

            # Subtitles tab
            if hasattr(self.player, "sub_mgr"):
                if hasattr(self, "size_scale"):
                    self.size_scale.set_value(self.player.sub_mgr.font_size)
                if hasattr(self, "sync_scale"):
                    self.sync_scale.set_value(self.player.sub_mgr.sync_offset_sec)
                if hasattr(self, "trans_check"):
                    self.trans_check.set_active(self.player.sub_mgr.translation_enabled)

            # Playback tab
            if hasattr(self, "speed_scale") and hasattr(self.player, "core"):
                self.speed_scale.set_value(self.player.core.speed)

            # Shaders tab
            if hasattr(self, "shader_checks") and hasattr(self.player, "shader_mgr"):
                for shader, chk in self.shader_checks.items():
                    is_active = any(shader in s for s in self.player.shader_mgr.active_shaders)
                    chk.set_active(is_active)
        finally:
            self._updating_controls = False

    def _create_audio_tab(self) -> Gtk.Widget:
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        vbox.set_margin_start(12)
        vbox.set_margin_end(12)
        vbox.set_margin_top(12)
        vbox.set_margin_bottom(12)

        # Top Controls: Enable Equalizer & Presets Dropdown
        top_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.eq_check = Gtk.CheckButton(label="Enable Equalizer")
        self.eq_check.set_active(self.player.equalizer.enabled)
        self.eq_check.connect("toggled", self._on_eq_toggled)
        top_box.pack_start(self.eq_check, False, False, 0)

        self.preset_combo = Gtk.ComboBoxText()
        for name in EQUALIZER_PRESETS.keys():
            self.preset_combo.append_text(name)
        self.preset_combo.set_active(0)
        self.preset_combo.connect("changed", self._on_preset_changed)
        top_box.pack_end(self.preset_combo, False, False, 0)
        top_box.pack_end(Gtk.Label(label="Preset:"), False, False, 0)
        vbox.pack_start(top_box, False, False, 0)

        # 10 vertical sliders for bands
        eq_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.eq_scales = []
        for i, freq in enumerate(FREQUENCIES):
            b_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            lbl = Gtk.Label(label=f"{freq if freq < 1000 else f'{freq//1000}k'}")
            scale = Gtk.Scale(orientation=Gtk.Orientation.VERTICAL,
                              adjustment=Gtk.Adjustment(value=self.player.equalizer.get_band(i), lower=-24.0, upper=12.0, step_increment=0.5, page_increment=2.0))
            scale.set_inverted(True)
            scale.set_vexpand(True)
            scale.connect("value-changed", self._make_band_callback(i))
            self.eq_scales.append(scale)
            b_box.pack_start(scale, True, True, 0)
            b_box.pack_start(lbl, False, False, 0)
            eq_box.pack_start(b_box, True, True, 0)

        vbox.pack_start(eq_box, True, True, 0)

        # Audio Enhancement Controls (loudness & dialogue clarity)
        enh_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.enhance_check = Gtk.CheckButton(label="Enable Audio Enhancement (Loudness & Speech Boost)")
        self.enhance_check.set_active(self.player.dsp.enhancement_enabled)
        self.enhance_check.connect("toggled", self._on_enhance_toggled)
        enh_box.pack_start(self.enhance_check, False, False, 0)

        enh_ctrl_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        enh_lbl = Gtk.Label(label="Preset:")
        enh_ctrl_box.pack_start(enh_lbl, False, False, 0)

        self.enhance_combo = Gtk.ComboBoxText()
        presets = ["Gentle / Low", "Balanced / Default", "Dialogue Focus", "Dynamic / High"]
        for p in presets:
            self.enhance_combo.append_text(p)
        cur_preset = self.player.dsp.enhancement_preset
        for idx, p in enumerate(presets):
            if p in cur_preset:
                self.enhance_combo.set_active(idx)
                break
        self.enhance_combo.connect("changed", self._on_enhance_preset_changed)
        enh_ctrl_box.pack_start(self.enhance_combo, True, True, 0)

        gain_lbl = Gtk.Label(label="Boost (dB):")
        enh_ctrl_box.pack_start(gain_lbl, False, False, 0)
        self.enhance_gain_scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0.0, 12.0, 0.5)
        self.enhance_gain_scale.set_value(self.player.dsp.enhancement_gain_db)
        self.enhance_gain_scale.set_hexpand(True)
        self.enhance_gain_scale.connect("value-changed", self._on_enhance_gain_changed)
        enh_ctrl_box.pack_start(self.enhance_gain_scale, True, True, 0)

        enh_box.pack_start(enh_ctrl_box, False, False, 0)
        vbox.pack_start(enh_box, False, False, 0)

        # Normalizer check
        self.norm_check = Gtk.CheckButton(label="Enable Dynamic Audio Normalizer")
        self.norm_check.set_active(self.player.dsp.normalizer_enabled)
        self.norm_check.connect("toggled", lambda w: self.player.toggle_normalizer(w.get_active()))
        vbox.pack_start(self.norm_check, False, False, 0)

        return vbox

    def _on_enhance_toggled(self, widget):
        if self._updating_controls:
            return
        if hasattr(self.player, "toggle_audio_enhancement"):
            self.player.toggle_audio_enhancement(widget.get_active())
            self.update_controls()

    def _on_enhance_preset_changed(self, combo):
        if self._updating_controls:
            return
        name = combo.get_active_text()
        if name and hasattr(self.player, "set_audio_enhancement_preset"):
            self.player.set_audio_enhancement_preset(name)
            if hasattr(self, "enhance_gain_scale"):
                self._updating_controls = True
                try:
                    self.enhance_gain_scale.set_value(self.player.dsp.enhancement_gain_db)
                finally:
                    self._updating_controls = False

    def _on_enhance_gain_changed(self, scale):
        if self._updating_controls:
            return
        if hasattr(self.player, "set_audio_enhancement_gain"):
            self.player.set_audio_enhancement_gain(scale.get_value())

    def _make_band_callback(self, idx: int):
        def _cb(scale):
            if self._updating_controls:
                return
            val = scale.get_value()
            self.player.equalizer.set_band(idx, val)
            self.player.apply_audio_filters()
        return _cb

    def _on_eq_toggled(self, widget):
        if self._updating_controls:
            return
        self.player.equalizer.enabled = widget.get_active()
        self.player.apply_audio_filters()

    def _on_preset_changed(self, combo):
        if self._updating_controls:
            return
        name = combo.get_active_text()
        if name and self.player.equalizer.apply_preset(name):
            self._updating_controls = True
            try:
                self.eq_check.set_active(True)
                for i, scale in enumerate(self.eq_scales):
                    scale.set_value(self.player.equalizer.get_band(i))
            finally:
                self._updating_controls = False
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
        if self._updating_controls:
            return
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
        self._updating_controls = True
        try:
            self.player.shader_mgr.reset_colors()
            self.bright_scale.set_value(0)
            self.contrast_scale.set_value(0)
            self.sat_scale.set_value(0)
            self.hue_scale.set_value(0)
        finally:
            self._updating_controls = False
        self._on_color_changed(None)

    def _create_subtitle_tab(self) -> Gtk.Widget:
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        vbox.set_margin_start(16)
        vbox.set_margin_end(16)
        vbox.set_margin_top(16)
        vbox.set_margin_bottom(16)

        # Font Size
        self.size_scale = self._add_slider_row(
            vbox, "Font Size:", 16, 80, self.player.sub_mgr.font_size,
            lambda s: None if self._updating_controls else self.player.set_subtitle_size(int(s.get_value()))
        )

        # Sync slider (-5s to +5s)
        def _on_sync_changed(s):
            if self._updating_controls:
                return
            val = s.get_value()
            self.player.sub_mgr.sync_offset_sec = val
            self.player.set_subtitle_sync(val)

        self.sync_scale = self._add_slider_row(
            vbox, "Sync (sec):", -5.0, 5.0, self.player.sub_mgr.sync_offset_sec,
            _on_sync_changed
        )

        # Translation check
        self.trans_check = Gtk.CheckButton(label="Enable Real-Time AI Subtitle Translation")
        self.trans_check.set_active(self.player.sub_mgr.translation_enabled)
        self.trans_check.connect("toggled", lambda w: None if self._updating_controls else self.player.toggle_translation(w.get_active()))
        vbox.pack_start(self.trans_check, False, False, 10)

        return vbox

    def _create_playback_tab(self) -> Gtk.Widget:
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        vbox.set_margin_start(16)
        vbox.set_margin_end(16)
        vbox.set_margin_top(16)
        vbox.set_margin_bottom(16)

        # Speed slider (supports up to 16.0x)
        self.speed_scale = self._add_slider_row(
            vbox, "Speed (x):", 0.1, 16.0, self.player.core.speed,
            lambda s: None if self._updating_controls else self.player.core.set_speed(s.get_value())
        )

        speed_btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        btn_reset_speed = Gtk.Button(label="Reset Speed (1.0x)")
        def _reset_speed(w):
            if not self._updating_controls:
                self.speed_scale.set_value(1.0)
                self.player.core.set_speed(1.0)
        btn_reset_speed.connect("clicked", _reset_speed)
        speed_btn_box.pack_start(btn_reset_speed, False, False, 0)
        vbox.pack_start(speed_btn_box, False, False, 0)

        # A-B Repeat Box
        ab_frame = Gtk.Frame(label="A-B Repeat Loop")
        ab_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        ab_box.set_margin_start(8)
        ab_box.set_margin_end(8)
        ab_box.set_margin_top(8)
        ab_box.set_margin_bottom(8)

        btn_a = Gtk.Button(label="Set A (Ctrl+[)")
        btn_a.set_tooltip_text("Set loop start point A ([ or Ctrl+[)")
        btn_a.connect("clicked", lambda w: self.player.set_repeat_a())
        btn_b = Gtk.Button(label="Set B (Ctrl+])")
        btn_b.set_tooltip_text("Set loop end point B (] or Ctrl+])")
        btn_b.connect("clicked", lambda w: self.player.set_repeat_b())
        btn_clear = Gtk.Button(label="Clear (Ctrl+\\)")
        btn_clear.set_tooltip_text("Clear A-B repeat loop (\\ or Ctrl+\\)")
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

        self.shader_checks = {}
        for shader in ["sharpen.hook", "adaptive_sharpen.hook", "denoise.hook"]:
            chk = Gtk.CheckButton(label=shader)
            is_active = any(shader in s for s in self.player.shader_mgr.active_shaders)
            chk.set_active(is_active)
            chk.connect("toggled", self._make_shader_toggle_cb(shader))
            self.shader_checks[shader] = chk
            vbox.pack_start(chk, False, False, 0)

        return vbox

    def _make_shader_toggle_cb(self, shader_name: str):
        def _cb(chk):
            if self._updating_controls:
                return
            if chk.get_active():
                self.player.shader_mgr.enable_shader(shader_name)
            else:
                self.player.shader_mgr.disable_shader(shader_name)
            self.player.core.set_glsl_shaders(self.player.shader_mgr.get_glsl_shaders_string())
        return _cb
