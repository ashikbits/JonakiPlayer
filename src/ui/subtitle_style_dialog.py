"""
Jonaki for Linux - Subtitle Style Configuration Dialog
Provides a comprehensive PotPlayer-like subtitle styling editor for fonts, colors, borders, shadows, margins, and positioning.
"""

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, Pango
from typing import Optional, Callable, Any
from subtitle.subtitle_manager import SubtitleStyle


def _hex_to_rgba(hex_code: str, alpha: float = 1.0) -> Gdk.RGBA:
    rgba = Gdk.RGBA()
    if not hex_code.startswith("#"):
        hex_code = "#" + hex_code
    # If 8-character hex (#AARRGGBB), convert to 6-char hex and extract alpha
    if len(hex_code) == 9:
        try:
            a_val = int(hex_code[1:3], 16) / 255.0
            r_val = int(hex_code[3:5], 16) / 255.0
            g_val = int(hex_code[5:7], 16) / 255.0
            b_val = int(hex_code[7:9], 16) / 255.0
            rgba.red = r_val
            rgba.green = g_val
            rgba.blue = b_val
            rgba.alpha = a_val
            return rgba
        except Exception:
            pass
    rgba.parse(hex_code[:7])
    rgba.alpha = alpha
    return rgba


def _rgba_to_hex(rgba: Gdk.RGBA) -> str:
    r = int(max(0.0, min(1.0, rgba.red)) * 255)
    g = int(max(0.0, min(1.0, rgba.green)) * 255)
    b = int(max(0.0, min(1.0, rgba.blue)) * 255)
    return f"#{r:02X}{g:02X}{b:02X}"


class SubtitleStyleDialog(Gtk.Dialog):
    """
    Comprehensive Subtitle Styling Configuration Dialog.
    Replicates PotPlayer's Subtitle Style Preferences.
    """
    def __init__(self, parent: Optional[Gtk.Window], current_style: SubtitleStyle,
                 on_apply: Callable[[SubtitleStyle], None]):
        super().__init__(title="Subtitle Style Settings - Jonaki",
                         transient_for=parent,
                         modal=True,
                         destroy_with_parent=True)
        self.set_default_size(680, 560)
        self.current_style = SubtitleStyle.from_dict(current_style.to_dict())
        self.on_apply = on_apply
        self._is_updating_preview = False

        self._setup_ui()
        self._apply_styling()
        self._load_from_style(self.current_style)
        self._update_preview()

    def _setup_ui(self) -> None:
        content_area = self.get_content_area()
        content_area.set_spacing(12)
        content_area.set_margin_top(14)
        content_area.set_margin_bottom(14)
        content_area.set_margin_start(16)
        content_area.set_margin_end(16)

        # Notebook for categorized tabs
        notebook = Gtk.Notebook()
        content_area.pack_start(notebook, True, True, 0)

        # --- TAB 1: Font & Typography ---
        font_page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        font_page.set_border_width(12)

        font_grid = Gtk.Grid()
        font_grid.set_column_spacing(12)
        font_grid.set_row_spacing(10)

        # Font Family & Picker
        lbl_font = Gtk.Label(label="Font:")
        lbl_font.set_halign(Gtk.Align.START)
        font_grid.attach(lbl_font, 0, 0, 1, 1)

        self.font_btn = Gtk.FontButton()
        self.font_btn.set_hexpand(True)
        self.font_btn.connect("font-set", self._on_font_button_set)
        font_grid.attach(self.font_btn, 1, 0, 2, 1)

        # Font Size
        lbl_size = Gtk.Label(label="Size (pt):")
        lbl_size.set_halign(Gtk.Align.START)
        font_grid.attach(lbl_size, 0, 1, 1, 1)

        self.size_spin = Gtk.SpinButton.new_with_range(12, 96, 1)
        self.size_spin.connect("value-changed", self._on_control_changed)
        font_grid.attach(self.size_spin, 1, 1, 1, 1)

        # Bold & Italic checkboxes
        style_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        self.bold_check = Gtk.CheckButton(label="Bold")
        self.bold_check.connect("toggled", self._on_control_changed)
        style_box.pack_start(self.bold_check, False, False, 0)

        self.italic_check = Gtk.CheckButton(label="Italic")
        self.italic_check.connect("toggled", self._on_control_changed)
        style_box.pack_start(self.italic_check, False, False, 0)
        font_grid.attach(style_box, 2, 1, 1, 1)

        # Letter Spacing
        lbl_spacing = Gtk.Label(label="Character Spacing:")
        lbl_spacing.set_halign(Gtk.Align.START)
        font_grid.attach(lbl_spacing, 0, 2, 1, 1)

        self.spacing_spin = Gtk.SpinButton.new_with_range(-5.0, 20.0, 0.5)
        self.spacing_spin.set_digits(1)
        self.spacing_spin.connect("value-changed", self._on_control_changed)
        font_grid.attach(self.spacing_spin, 1, 2, 1, 1)

        # ASS Subtitle Override
        lbl_ass = Gtk.Label(label="Override ASS Style:")
        lbl_ass.set_halign(Gtk.Align.START)
        font_grid.attach(lbl_ass, 0, 3, 1, 1)

        self.ass_combo = Gtk.ComboBoxText()
        self.ass_combo.append("scale", "Scale (Preserve layout, scale font)")
        self.ass_combo.append("yes", "Yes (Override fonts & colors)")
        self.ass_combo.append("force", "Force (Strict override)")
        self.ass_combo.append("strip", "Strip (Remove styling completely)")
        self.ass_combo.append("no", "No (Render embedded styles only)")
        self.ass_combo.connect("changed", self._on_control_changed)
        font_grid.attach(self.ass_combo, 1, 3, 2, 1)

        font_page.pack_start(font_grid, False, False, 0)
        notebook.append_page(font_page, Gtk.Label(label="Font & Text"))

        # --- TAB 2: Colors & Effects ---
        color_page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        color_page.set_border_width(12)

        color_grid = Gtk.Grid()
        color_grid.set_column_spacing(12)
        color_grid.set_row_spacing(10)

        # Primary Font Color
        lbl_pcol = Gtk.Label(label="Primary Text Color:")
        lbl_pcol.set_halign(Gtk.Align.START)
        color_grid.attach(lbl_pcol, 0, 0, 1, 1)

        self.primary_color_btn = Gtk.ColorButton()
        self.primary_color_btn.connect("color-set", self._on_control_changed)
        color_grid.attach(self.primary_color_btn, 1, 0, 1, 1)

        # Outline (Border) Color & Size
        lbl_ocol = Gtk.Label(label="Outline / Border Color:")
        lbl_ocol.set_halign(Gtk.Align.START)
        color_grid.attach(lbl_ocol, 0, 1, 1, 1)

        self.outline_color_btn = Gtk.ColorButton()
        self.outline_color_btn.connect("color-set", self._on_control_changed)
        color_grid.attach(self.outline_color_btn, 1, 1, 1, 1)

        lbl_owidth = Gtk.Label(label="Outline Width (px):")
        lbl_owidth.set_halign(Gtk.Align.START)
        color_grid.attach(lbl_owidth, 2, 1, 1, 1)

        self.outline_spin = Gtk.SpinButton.new_with_range(0.0, 10.0, 0.5)
        self.outline_spin.set_digits(1)
        self.outline_spin.connect("value-changed", self._on_control_changed)
        color_grid.attach(self.outline_spin, 3, 1, 1, 1)

        # Shadow Color & Offset
        lbl_scol = Gtk.Label(label="Drop Shadow Color:")
        lbl_scol.set_halign(Gtk.Align.START)
        color_grid.attach(lbl_scol, 0, 2, 1, 1)

        self.shadow_color_btn = Gtk.ColorButton()
        self.shadow_color_btn.connect("color-set", self._on_control_changed)
        color_grid.attach(self.shadow_color_btn, 1, 2, 1, 1)

        lbl_soffset = Gtk.Label(label="Shadow Offset (px):")
        lbl_soffset.set_halign(Gtk.Align.START)
        color_grid.attach(lbl_soffset, 2, 2, 1, 1)

        self.shadow_spin = Gtk.SpinButton.new_with_range(0.0, 15.0, 0.5)
        self.shadow_spin.set_digits(1)
        self.shadow_spin.connect("value-changed", self._on_control_changed)
        color_grid.attach(self.shadow_spin, 3, 2, 1, 1)

        # Background Box Color & Opacity
        lbl_bcol = Gtk.Label(label="Background Box Color:")
        lbl_bcol.set_halign(Gtk.Align.START)
        color_grid.attach(lbl_bcol, 0, 3, 1, 1)

        self.back_color_btn = Gtk.ColorButton()
        self.back_color_btn.connect("color-set", self._on_control_changed)
        color_grid.attach(self.back_color_btn, 1, 3, 1, 1)

        lbl_balpha = Gtk.Label(label="Background Opacity (%):")
        lbl_balpha.set_halign(Gtk.Align.START)
        color_grid.attach(lbl_balpha, 2, 3, 1, 1)

        self.back_alpha_spin = Gtk.SpinButton.new_with_range(0, 100, 5)
        self.back_alpha_spin.connect("value-changed", self._on_control_changed)
        color_grid.attach(self.back_alpha_spin, 3, 3, 1, 1)

        color_page.pack_start(color_grid, False, False, 0)
        notebook.append_page(color_page, Gtk.Label(label="Colors & Effects"))

        # --- TAB 3: Position & Alignment ---
        pos_page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        pos_page.set_border_width(12)

        pos_grid = Gtk.Grid()
        pos_grid.set_column_spacing(12)
        pos_grid.set_row_spacing(10)

        # Vertical Position (%)
        lbl_pos = Gtk.Label(label="Vertical Position (%):")
        lbl_pos.set_halign(Gtk.Align.START)
        pos_grid.attach(lbl_pos, 0, 0, 1, 1)

        self.pos_spin = Gtk.SpinButton.new_with_range(0, 150, 1)
        self.pos_spin.connect("value-changed", self._on_control_changed)
        pos_grid.attach(self.pos_spin, 1, 0, 1, 1)

        # Margin Y (Vertical Margin px)
        lbl_my = Gtk.Label(label="Vertical Margin (px):")
        lbl_my.set_halign(Gtk.Align.START)
        pos_grid.attach(lbl_my, 2, 0, 1, 1)

        self.margin_y_spin = Gtk.SpinButton.new_with_range(0, 200, 2)
        self.margin_y_spin.connect("value-changed", self._on_control_changed)
        pos_grid.attach(self.margin_y_spin, 3, 0, 1, 1)

        # Margin X (Horizontal Margin px)
        lbl_mx = Gtk.Label(label="Horizontal Margin (px):")
        lbl_mx.set_halign(Gtk.Align.START)
        pos_grid.attach(lbl_mx, 0, 1, 1, 1)

        self.margin_x_spin = Gtk.SpinButton.new_with_range(0, 200, 2)
        self.margin_x_spin.connect("value-changed", self._on_control_changed)
        pos_grid.attach(self.margin_x_spin, 1, 1, 1, 1)

        # Horizontal Alignment
        lbl_halign = Gtk.Label(label="Horizontal Alignment:")
        lbl_halign.set_halign(Gtk.Align.START)
        pos_grid.attach(lbl_halign, 0, 2, 1, 1)

        self.align_x_combo = Gtk.ComboBoxText()
        self.align_x_combo.append("center", "Center")
        self.align_x_combo.append("left", "Left")
        self.align_x_combo.append("right", "Right")
        self.align_x_combo.connect("changed", self._on_control_changed)
        pos_grid.attach(self.align_x_combo, 1, 2, 1, 1)

        # Vertical Alignment
        lbl_valign = Gtk.Label(label="Vertical Alignment:")
        lbl_valign.set_halign(Gtk.Align.START)
        pos_grid.attach(lbl_valign, 2, 2, 1, 1)

        self.align_y_combo = Gtk.ComboBoxText()
        self.align_y_combo.append("bottom", "Bottom")
        self.align_y_combo.append("top", "Top")
        self.align_y_combo.append("center", "Center")
        self.align_y_combo.connect("changed", self._on_control_changed)
        pos_grid.attach(self.align_y_combo, 3, 2, 1, 1)

        pos_page.pack_start(pos_grid, False, False, 0)
        notebook.append_page(pos_page, Gtk.Label(label="Position & Alignment"))

        # --- LIVE PREVIEW AREA ---
        preview_frame = Gtk.Frame(label="Live Preview")
        preview_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        preview_box.set_size_request(-1, 90)

        # Black background eventbox to simulate video overlay
        self.preview_eb = Gtk.EventBox()
        self.preview_eb.override_background_color(Gtk.StateFlags.NORMAL, Gdk.RGBA(0.08, 0.08, 0.08, 1.0))

        self.preview_label = Gtk.Label()
        self.preview_label.set_text("Jonaki - PotPlayer Subtitle Styling")
        self.preview_label.set_justify(Gtk.Justification.CENTER)
        self.preview_label.set_margin_top(15)
        self.preview_label.set_margin_bottom(15)
        self.preview_eb.add(self.preview_label)

        preview_box.pack_start(self.preview_eb, True, True, 0)
        preview_frame.add(preview_box)
        content_area.pack_start(preview_frame, False, False, 0)

        # --- DIALOG ACTION BUTTONS ---
        self.add_button("Reset to Default", 100)
        self.add_button("Cancel", Gtk.ResponseType.CANCEL)
        self.apply_btn = self.add_button("Apply", 101)
        self.ok_btn = self.add_button("OK", Gtk.ResponseType.OK)

        self.connect("response", self._on_dialog_response)

    def _apply_styling(self) -> None:
        css_provider = Gtk.CssProvider()
        css = b"""
        dialog {
            background-color: #1e1e1e;
            color: #dcdcdc;
        }
        notebook tab {
            background-color: #2b2b2b;
            color: #bbbbbb;
            padding: 6px 14px;
        }
        notebook tab:checked {
            background-color: #383838;
            color: #ffffff;
            font-weight: bold;
        }
        label {
            color: #e0e0e0;
        }
        frame {
            border: 1px solid #444444;
            border-radius: 4px;
        }
        """
        css_provider.load_from_data(css)
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(),
            css_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

    def _load_from_style(self, style: SubtitleStyle) -> None:
        self._is_updating_preview = True

        # Font description
        weight_str = " Bold" if style.bold else ""
        slant_str = " Italic" if style.italic else ""
        font_str = f"{style.font_family}{weight_str}{slant_str} {int(style.font_size)}"
        self.font_btn.set_font(font_str)

        self.size_spin.set_value(style.font_size)
        self.bold_check.set_active(style.bold)
        self.italic_check.set_active(style.italic)
        self.spacing_spin.set_value(style.spacing)
        self.ass_combo.set_active_id(style.ass_override)

        # Colors
        self.primary_color_btn.set_rgba(_hex_to_rgba(style.primary_color))
        self.outline_color_btn.set_rgba(_hex_to_rgba(style.outline_color))
        self.outline_spin.set_value(style.outline_width)
        self.shadow_color_btn.set_rgba(_hex_to_rgba(style.shadow_color))
        self.shadow_spin.set_value(style.shadow_offset)
        self.back_color_btn.set_rgba(_hex_to_rgba(style.back_color))
        self.back_alpha_spin.set_value(int(style.back_alpha * 100))

        # Position
        self.pos_spin.set_value(style.pos)
        self.margin_y_spin.set_value(style.margin_y)
        self.margin_x_spin.set_value(style.margin_x)
        self.align_x_combo.set_active_id(style.align_x)
        self.align_y_combo.set_active_id(style.align_y)

        self._is_updating_preview = False

    def _collect_style(self) -> SubtitleStyle:
        style = SubtitleStyle()

        # Font
        font_name = self.font_btn.get_font() or "sans-serif 48"
        pango_desc = Pango.FontDescription.from_string(font_name)
        style.font_family = pango_desc.get_family() or "sans-serif"
        style.font_size = int(self.size_spin.get_value())
        style.bold = self.bold_check.get_active()
        style.italic = self.italic_check.get_active()
        style.spacing = round(self.spacing_spin.get_value(), 1)
        style.ass_override = self.ass_combo.get_active_id() or "scale"

        # Colors
        style.primary_color = _rgba_to_hex(self.primary_color_btn.get_rgba())
        style.outline_color = _rgba_to_hex(self.outline_color_btn.get_rgba())
        style.outline_width = round(self.outline_spin.get_value(), 1)
        style.shadow_color = _rgba_to_hex(self.shadow_color_btn.get_rgba())
        style.shadow_offset = round(self.shadow_spin.get_value(), 1)
        style.back_color = _rgba_to_hex(self.back_color_btn.get_rgba())
        style.back_alpha = round(self.back_alpha_spin.get_value() / 100.0, 2)

        # Position
        style.pos = int(self.pos_spin.get_value())
        style.margin_y = int(self.margin_y_spin.get_value())
        style.margin_x = int(self.margin_x_spin.get_value())
        style.align_x = self.align_x_combo.get_active_id() or "center"
        style.align_y = self.align_y_combo.get_active_id() or "bottom"

        return style

    def _on_font_button_set(self, btn: Gtk.FontButton) -> None:
        if self._is_updating_preview:
            return
        font_name = btn.get_font()
        if font_name:
            pdesc = Pango.FontDescription.from_string(font_name)
            self._is_updating_preview = True
            sz = int(pdesc.get_size() / Pango.SCALE)
            if sz > 0:
                self.size_spin.set_value(sz)
            self.bold_check.set_active(pdesc.get_weight() >= Pango.Weight.BOLD)
            self.italic_check.set_active(pdesc.get_style() != Pango.Style.NORMAL)
            self._is_updating_preview = False
        self._update_preview()

    def _on_control_changed(self, *args) -> None:
        if self._is_updating_preview:
            return
        self._update_preview()

    def _update_preview(self) -> None:
        style = self._collect_style()
        self.current_style = style

        # Render preview label markup
        weight_tag = "bold" if style.bold else "normal"
        slant_tag = "italic" if style.italic else "normal"
        color_hex = style.primary_color

        # Preview size scaled down for dialog
        preview_pt = max(14, min(36, int(style.font_size * 0.5)))
        markup = (f'<span font_family="{style.font_family}" size="{preview_pt * 1024}" '
                  f'weight="{weight_tag}" style="{slant_tag}" foreground="{color_hex}">'
                  f'Jonaki Subtitle Preview</span>')
        self.preview_label.set_markup(markup)

        # Background preview tint
        if style.back_alpha > 0.0:
            bg_rgba = _hex_to_rgba(style.back_color, style.back_alpha)
            self.preview_eb.override_background_color(Gtk.StateFlags.NORMAL, bg_rgba)
        else:
            self.preview_eb.override_background_color(Gtk.StateFlags.NORMAL, Gdk.RGBA(0.08, 0.08, 0.08, 1.0))

    def _on_dialog_response(self, dialog, response_id: int) -> None:
        if response_id == 100:  # Reset to Default
            self.current_style = SubtitleStyle()
            self._load_from_style(self.current_style)
            self._update_preview()
            if self.on_apply:
                self.on_apply(self.current_style)
        elif response_id == 101:  # Apply
            self.current_style = self._collect_style()
            if self.on_apply:
                self.on_apply(self.current_style)
        elif response_id == Gtk.ResponseType.OK:
            self.current_style = self._collect_style()
            if self.on_apply:
                self.on_apply(self.current_style)
            self.destroy()
        elif response_id in (Gtk.ResponseType.CANCEL, Gtk.ResponseType.DELETE_EVENT):
            self.destroy()
