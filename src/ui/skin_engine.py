"""
Jonaki for Linux - DSF Skin Parser & Cairo Sprite Renderer
Parses authentic .dsf ZIP archives, extracts sprite sheets, and renders
the pixel-accurate user interface.
"""

import os
import zipfile
import io
import math
from typing import Dict, List, Optional, Tuple, Any
import cairo


class SkinButton:
    def __init__(self, cmd_id: str, tooltip: str, width: int, height: int,
                 img_left: int, img_top: int, img_width: int, img_height: int,
                 align: str = "Left", min_parent_width: int = 0):
        self.cmd_id = cmd_id
        self.tooltip = tooltip
        self.width = width
        self.height = height
        self.img_left = img_left
        self.img_top = img_top
        self.img_width = img_width
        self.img_height = img_height
        self.align = align
        self.min_parent_width = min_parent_width

        # Runtime hit-test box (x, y, w, h)
        self.rect: Tuple[int, int, int, int] = (0, 0, width, height)
        self.state: int = 0  # 0=Normal, 1=Hover, 2=Pressed, 3=Disabled
        self.label_text: Optional[str] = None
        self.active: bool = False


class SkinSlider:
    def __init__(self, cmd_id: str, width: int, height: int,
                 track_img_left: int, track_img_top: int,
                 thumb_img_left: int, thumb_img_top: int,
                 thumb_width: int = 11, thumb_height: int = 10,
                 fill_img_left: int = 0, fill_img_top: int = 0,
                 left_margin: int = 10, right_margin: int = 10):
        self.cmd_id = cmd_id
        self.width = width
        self.height = height
        self.track_img_left = track_img_left
        self.track_img_top = track_img_top
        self.thumb_img_left = thumb_img_left
        self.thumb_img_top = thumb_img_top
        self.thumb_width = thumb_width
        self.thumb_height = thumb_height
        self.fill_img_left = fill_img_left
        self.fill_img_top = fill_img_top
        self.left_margin = left_margin
        self.right_margin = right_margin

        self.rect: Tuple[int, int, int, int] = (0, 0, width, height)
        self.value: float = 0.0  # 0.0 to 1.0
        self.is_dragging: bool = False
        self.state: int = 0      # 0=Normal, 1=Hover, 2=Down


def clean_codec_name(raw: str) -> str:
    """Normalizes raw codec strings to short badge labels."""
    if not raw:
        return ""
    u = raw.upper()
    if "AV1" in u:
        return "AV1"
    if "HEVC" in u or "H.265" in u or "H265" in u:
        return "HEVC"
    if "H.264" in u or "H264" in u or "AVC" in u:
        return "H264"
    if "VP9" in u:
        return "VP9"
    if "VP8" in u:
        return "VP8"
    if "OPUS" in u:
        return "OPUS"
    if "AAC" in u:
        return "AAC"
    if "FLAC" in u:
        return "FLAC"
    if "MP3" in u:
        return "MP3"
    if "VORBIS" in u:
        return "VORBIS"
    if "EAC3" in u or "E-AC-3" in u:
        return "E-AC3"
    if "AC3" in u or "AC-3" in u:
        return "AC3"
    if "DTS" in u:
        return "DTS"
    tokens = raw.split()
    return tokens[0][:6].upper() if tokens else ""


class PotSkinEngine:
    """
    Extracts and parses .dsf skins into Cairo image surfaces and renders
    the authentic sprite-based user interface.
    """
    def __init__(self, dsf_path: Optional[str] = None):
        if dsf_path is None:
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            dsf_path = os.path.join(base_dir, "assets", "skins", "Default.dsf")
        self.dsf_path = dsf_path
        self.surfaces: Dict[str, cairo.ImageSurface] = {}
        self.buttons: List[SkinButton] = []
        self.timebar: Optional[SkinSlider] = None
        self.volume_slider: Optional[SkinSlider] = None
        self.badges: List[SkinButton] = []
        self.scale_factor: float = 1.0

        self._init_default_controls()
        self._load_dsf()

    def _load_dsf(self) -> None:
        # Load native Jonaki logo asset if available on disk
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        jonaki_logo_candidates = [
            os.path.join(base_dir, "assets", "logos", "jonaki.png"),
            os.path.expanduser("~/.local/share/icons/hicolor/256x256/apps/jonaki.png"),
            "/usr/share/icons/hicolor/256x256/apps/jonaki.png",
        ]
        for candidate in jonaki_logo_candidates:
            if os.path.exists(candidate):
                try:
                    self.surfaces["jonaki.png"] = cairo.ImageSurface.create_from_png(candidate)
                    break
                except Exception as e:
                    print(f"[SkinEngine] Error loading logo {candidate}: {e}")

        if not os.path.exists(self.dsf_path):
            print(f"[SkinEngine] Skin not found: {self.dsf_path}")
            return

        try:
            with zipfile.ZipFile(self.dsf_path, "r") as z:
                for filename in z.namelist():
                    if filename.lower().endswith(".png"):
                        png_bytes = z.read(filename)
                        try:
                            surf = cairo.ImageSurface.create_from_png(io.BytesIO(png_bytes))
                            self.surfaces[filename] = surf
                            if "logo" in filename.lower() or "player" in filename.lower():
                                self.surfaces.setdefault("dsf_logo.png", surf)
                        except Exception as e:
                            print(f"[SkinEngine] Error loading {filename}: {e}")
        except Exception as e:
            print(f"[SkinEngine] Failed to open DSF archive: {e}")

    def _init_default_controls(self) -> None:
        """
        Builds the standard control layout extracted from BottomVideo.txt:
        Play, Pause, Stop, Seek Back 5s, Seek Forw 5s, Open File, Timebar, Badges, Volume.
        """
        # Primary playback buttons (Main.png, 41x40, 4 horizontal states)
        self.btn_play = SkinButton("CMD_MEDIA_PLAY", "Play (Space)", 41, 40, 0, 259, 41, 40)
        self.btn_pause = SkinButton("CMD_MEDIA_PAUSE", "Pause (Space)", 41, 40, 164, 259, 41, 40)
        self.btn_stop = SkinButton("CMD_MEDIA_CLOSE", "Stop (F4)", 41, 40, 0, 300, 41, 40)
        self.btn_prev = SkinButton("ID_PLAYBACK_5SEC_BACK", "Seek -5s (Left)", 41, 40, 164, 300, 41, 40)
        self.btn_next = SkinButton("ID_PLAYBACK_5SEC_FORW", "Seek +5s (Right)", 41, 40, 328, 300, 41, 40)
        self.btn_open = SkinButton("ID_BASE_OPEN", "Open File (Ctrl+O / F3)", 41, 40, 0, 341, 41, 40)

        # Upper strip buttons
        self.btn_mute = SkinButton("ID_AUDIO_MUTE", "Mute Audio", 13, 10, 175, 167, 13, 10, align="Right")

        # Right-side buttons (Main.png, 23x22)
        self.btn_stream = SkinButton("CMD_POPUPMENU_STREAM_SELECT", "Stream / Source Select", 23, 22, 202, 455, 23, 22, align="Right")
        self.btn_playlist = SkinButton("ID_PLAYLIST_WINDOW", "Playlist (F8 / F12)", 23, 22, 202, 391, 23, 22, align="Right")
        self.btn_control_box = SkinButton("ID_CONTROL_BOX_WINDOW", "Control Box (F6)", 23, 22, 303, 391, 23, 22, align="Right")
        self.btn_fullscreen = SkinButton("CMD_FULLSCREEN", "Fullscreen (Enter)", 23, 22, 101, 391, 23, 22, align="Right")

        self.buttons = [
            self.btn_play,
            self.btn_pause,
            self.btn_stop,
            self.btn_prev,
            self.btn_next,
            self.btn_open,
            self.btn_mute,
            self.btn_stream,
            self.btn_playlist,
            self.btn_control_box,
            self.btn_fullscreen
        ]

        # Timebar seek slider (Upper strip: 10px height, 3-slice track & thumb)
        self.timebar = SkinSlider("CMD_TIMEBAR_CTRL", width=300, height=10,
                                  track_img_left=0, track_img_top=193,
                                  thumb_img_left=1, thumb_img_top=239,
                                  thumb_width=11, thumb_height=10,
                                  fill_img_left=0, fill_img_top=179,
                                  left_margin=10, right_margin=10)

        # Volume slider (Upper strip right: 70px width, 10px height)
        self.volume_slider = SkinSlider("CMD_VOLUME_CTRL", width=70, height=10,
                                        track_img_left=175, track_img_top=207,
                                        thumb_img_left=85, thumb_img_top=239,
                                        thumb_width=11, thumb_height=10,
                                        fill_img_left=175, fill_img_top=194,
                                        left_margin=5, right_margin=5)
        self.volume_slider.value = 0.8  # Default 80%

        # Dynamic Status Badges (Main.png 485, 34, 41, 14 3-slice pill)
        self.badge_hw = SkinButton("CMD_VIDEO_OUT_HW_SW_MESSAGE", "Hardware Acceleration (Click to Toggle)", 40, 14, 485, 34, 41, 14, min_parent_width=450)
        self.badge_hw.label_text = "HW"

        self.badge_hdr = SkinButton("ID_VIDEO_PS_SMPTE_2084", "HDR Tone-mapping (Click to Toggle)", 42, 14, 485, 34, 41, 14, min_parent_width=510)
        self.badge_hdr.label_text = "HDR"

        self.badge_video = SkinButton("CMD_VIDEO_CODEC_FOURCC_MESSAGE", "Video Codec (Click for Media Information Ctrl+F1)", 44, 14, 485, 34, 41, 14, min_parent_width=580)
        self.badge_video.label_text = "AV1"

        self.badge_audio = SkinButton("CMD_AUDIO_CODEC_TYPE_MESSAGE", "Audio Codec (Click to Cycle Track)", 48, 14, 485, 34, 41, 14, min_parent_width=650)
        self.badge_audio.label_text = "OPUS"

        self.badge_channel = SkinButton("CMD_AUDIO_OUT_NUM_CHANNEL_MESSAGE", "Audio Channels (Click for Equalizer & DSP)", 36, 14, 485, 34, 41, 14, min_parent_width=710)
        self.badge_channel.label_text = "2.0"

        self.badges = [
            self.badge_hw,
            self.badge_hdr,
            self.badge_video,
            self.badge_audio,
            self.badge_channel
        ]

    @staticmethod
    def draw_3slice(cr: cairo.Context, surf: cairo.ImageSurface,
                    dx: int, dy: int, dw: int, dh: int,
                    sx: int, sy: int, sw: int, sh: int,
                    lm: int, rm: int) -> None:
        """
        Renders a 3-slice horizontal sprite: fixed left cap, stretched middle, fixed right cap.
        """
        if dw <= 0 or dh <= 0 or not surf:
            return
        clm = min(lm, dw // 2)
        crm = min(rm, dw // 2)

        # Left cap
        if clm > 0:
            cr.save()
            cr.rectangle(dx, dy, clm, dh)
            cr.clip()
            cr.set_source_surface(surf, dx - sx, dy - sy)
            cr.paint()
            cr.restore()

        # Right cap
        if crm > 0:
            cr.save()
            cr.rectangle(dx + dw - crm, dy, crm, dh)
            cr.clip()
            cr.set_source_surface(surf, (dx + dw) - (sx + sw), dy - sy)
            cr.paint()
            cr.restore()

        # Middle stretch
        mid_dw = dw - clm - crm
        mid_sw = sw - lm - rm
        if mid_dw > 0 and mid_sw > 0:
            cr.save()
            cr.rectangle(dx + clm, dy, mid_dw, dh)
            cr.clip()
            cr.translate(dx + clm, dy)
            cr.scale(mid_dw / mid_sw, dh / sh)
            cr.set_source_surface(surf, -(sx + lm), -sy)
            cr.paint()
            cr.restore()

    def layout(self, panel_width: int, panel_height: int = 62, is_playing: bool = False, min_badge_x: int = 330) -> None:
        """
        Computes coordinate bounds for all widgets across the panel dimensions.
        Total height is partitioned into 22px upper strip (timebar & volume) and
        40px lower strip (transport, time text, badges, and right tool buttons).
        """
        upper_h = 22
        lower_y = upper_h
        lower_h = max(30, panel_height - upper_h)

        # --- 1. Upper Strip: Volume Slider, Mute, Timebar ---
        vol_w = 70
        vol_h = 10
        vol_x = panel_width - 12 - vol_w
        vol_y = (upper_h - vol_h) // 2
        if self.volume_slider:
            self.volume_slider.rect = (vol_x, vol_y, vol_w, vol_h)

        mute_w = 13
        mute_h = 10
        mute_x = vol_x - mute_w - 6
        mute_y = (upper_h - mute_h) // 2
        self.btn_mute.rect = (mute_x, mute_y, mute_w, mute_h)

        tb_x = 10
        tb_y = (upper_h - 10) // 2
        tb_w = max(40, mute_x - 14 - tb_x)
        if self.timebar:
            self.timebar.rect = (tb_x, tb_y, tb_w, 10)

        # --- 2. Lower Strip: Transport Buttons (Left) ---
        btn_y = lower_y + (lower_h - 40) // 2
        self.btn_play.rect = (0, btn_y, 41, 40)
        self.btn_pause.rect = (0, btn_y, 41, 40)
        self.btn_stop.rect = (41, btn_y, 41, 40)
        self.btn_prev.rect = (82, btn_y, 41, 40)
        self.btn_next.rect = (123, btn_y, 41, 40)
        self.btn_open.rect = (164, btn_y, 41, 40)

        # --- 3. Lower Strip: Tool Buttons (Right) ---
        rx = panel_width - 10
        for btn in [self.btn_fullscreen, self.btn_control_box, self.btn_playlist, self.btn_stream]:
            rx -= btn.width
            btn.rect = (rx, lower_y + (lower_h - btn.height) // 2, btn.width, btn.height)
            rx -= 6
        max_badge_x = rx - 10

        # --- 4. Lower Strip: Badges ---
        badge_x = max(330, min_badge_x)
        badge_h = 14
        badge_y = lower_y + (lower_h - badge_h) // 2
        for badge in self.badges:
            # Dynamic width calculation
            text = badge.label_text or ""
            bw = max(badge.width, len(text) * 8 + 14)
            if badge_x + bw < max_badge_x and panel_width >= badge.min_parent_width:
                badge.rect = (badge_x, badge_y, bw, badge_h)
                badge_x += bw + 5
            else:
                badge.rect = (-100, -100, 0, 0)

    def render(self, cr: cairo.Context, panel_width: int, panel_height: int = 62,
               is_playing: bool = True, position_sec: float = 0.0, duration_sec: float = 0.0,
               repeat_a: Optional[float] = None, repeat_b: Optional[float] = None,
               bookmarks: Optional[List[float]] = None,
               chapters: Optional[List[float]] = None,
               media_info: Optional[Dict[str, Any]] = None,
               scale_factor: Optional[float] = None) -> None:
        """
        Renders the complete control bar surface using authentic DSF sprites.
        Supports dynamic HiDPI scaling without coordinate drift.
        """
        if scale_factor is not None:
            self.scale_factor = max(0.5, float(scale_factor))

        main_surf = self.surfaces.get("Main.png")
        if not main_surf:
            return

        cr.save()
        if self.scale_factor != 1.0:
            cr.scale(self.scale_factor, self.scale_factor)
            panel_width = int(panel_width / self.scale_factor)
            panel_height = int(panel_height / self.scale_factor)

        if position_sec is None or math.isnan(position_sec) or math.isinf(position_sec):
            position_sec = 0.0
        position_sec = max(0.0, position_sec)

        if duration_sec is None or math.isnan(duration_sec) or math.isinf(duration_sec):
            duration_sec = 0.0
        duration_sec = max(0.0, duration_sec)

        # Dynamic time formatting with duration-aware hour symmetrization
        curr_str = self._format_time(position_sec, duration_sec)
        total_str = self._format_time(duration_sec, duration_sec)
        time_x = 215

        cr.save()
        cr.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
        cr.set_font_size(11.0)
        curr_ext = cr.text_extents(curr_str)
        slash_ext = cr.text_extents("/")
        tot_ext = cr.text_extents(total_str)
        cr.restore()

        time_w = curr_ext.x_advance + 4 + slash_ext.x_advance + 4 + tot_ext.x_advance
        needed_badge_x = max(330, int(time_x + time_w + 14))
        self.layout(panel_width, panel_height, is_playing=is_playing, min_badge_x=needed_badge_x)

        upper_h = 22
        lower_y = upper_h
        lower_h = max(30, panel_height - upper_h)

        # 1. Backgrounds (Authentic 3-slice brushed panels)
        # Upper strip background: ImageLeft=3, ImageTop=668, ImageWidth=306, ImageHeight=22
        self.draw_3slice(cr, main_surf, 0, 0, panel_width, upper_h, 3, 668, 306, 22, 10, 10)
        # Lower strip background: ImageLeft=3, ImageTop=690, ImageWidth=306, ImageHeight=40
        self.draw_3slice(cr, main_surf, 0, lower_y, panel_width, lower_h, 3, 690, 306, 40, 10, 10)

        # 2. Upper Strip: Timebar Seek Slider
        if self.timebar:
            tx, ty, tw, th = self.timebar.rect
            if getattr(self.timebar, "is_dragging", False) and getattr(self.timebar, "drag_ratio", None) is not None:
                progress = self.timebar.drag_ratio
            else:
                progress = (position_sec / duration_sec) if duration_sec > 0 else 0.0
            progress = max(0.0, min(1.0, progress))

            # Background track (0, 193, 95, 10)
            self.draw_3slice(cr, main_surf, tx, ty, tw, th, 0, 193, 95, 10, 10, 10)

            # Played progress fill track (0, 179, 95, 10)
            fill_w = int(tw * progress)
            if fill_w > 0:
                self.draw_3slice(cr, main_surf, tx, ty, fill_w, th, 0, 179, 95, 10, 10, 10)

            # A-B Repeat Loop segment markers
            if repeat_a is not None and duration_sec > 0:
                ax = max(tx, min(tx + tw - 6, tx + int((repeat_a / duration_sec) * tw)))
                cr.save()
                cr.rectangle(ax, ty, 6, 10)
                cr.clip()
                cr.set_source_surface(main_surf, ax - 148, ty - 241)
                cr.paint()
                cr.restore()

            if repeat_b is not None and duration_sec > 0:
                bx = max(tx, min(tx + tw - 6, tx + int((repeat_b / duration_sec) * tw)))
                cr.save()
                cr.rectangle(bx, ty, 6, 10)
                cr.clip()
                cr.set_source_surface(main_surf, bx - 155, ty - 241)
                cr.paint()
                cr.restore()

            # Bookmarks pins (gold markers)
            if bookmarks and duration_sec > 0:
                for bm_pts in bookmarks:
                    bm_x = max(tx, min(tx + tw, tx + int((bm_pts / duration_sec) * tw)))
                    cr.save()
                    # Subtle dark outline / drop shadow
                    cr.set_source_rgba(0.0, 0.0, 0.0, 0.85)
                    cr.rectangle(bm_x - 1.5, ty - 1, 4, th + 2)
                    cr.fill()
                    # Crisp gold marker line
                    cr.set_source_rgb(1.0, 0.84, 0.0)  # Gold #FFD700
                    cr.rectangle(bm_x - 0.5, ty, 2.0, th)
                    cr.fill()
                    # Top diamond pip
                    cr.move_to(bm_x + 0.5, ty - 2)
                    cr.line_to(bm_x + 3.0, ty + 1)
                    cr.line_to(bm_x + 0.5, ty + 4)
                    cr.line_to(bm_x - 2.0, ty + 1)
                    cr.close_path()
                    cr.fill()
                    cr.restore()

            # Chapter tick markers (crisp silver dividers along the seek track)
            if chapters and duration_sec > 0:
                for ch_pts in chapters:
                    if ch_pts > 0:
                        cx = max(tx, min(tx + tw, tx + int((ch_pts / duration_sec) * tw)))
                        cr.save()
                        cr.set_source_rgba(0.0, 0.0, 0.0, 0.7)
                        cr.rectangle(cx - 0.5, ty, 2.0, th)
                        cr.fill()
                        cr.set_source_rgba(0.85, 0.85, 0.90, 0.85)
                        cr.rectangle(cx, ty, 1.0, th)
                        cr.fill()
                        cr.restore()

            # Thumb Playhead knob (1, 239, 11, 10; hover/down at offset +14)
            tt_x = tx + int(tw * progress) - 5
            thumb_offset = 14 * self.timebar.state
            cr.save()
            cr.rectangle(tt_x, ty, 11, 10)
            cr.clip()
            cr.set_source_surface(main_surf, tt_x - (1 + thumb_offset), ty - 239)
            cr.paint()
            cr.restore()

        # 3. Upper Strip: Mute Button & Volume Slider
        is_muted = False
        if media_info:
            is_muted = media_info.get("is_muted", False)

        # Mute button (175, 167, 13, 10)
        mx, my, mw, mh = self.btn_mute.rect
        mute_src_x = 175 + (26 if is_muted else (self.btn_mute.state * 13))
        cr.save()
        cr.rectangle(mx, my, mw, mh)
        cr.clip()
        cr.set_source_surface(main_surf, mx - mute_src_x, my - 167)
        cr.paint()
        cr.restore()

        # Volume slider
        if self.volume_slider:
            vx, vy, vw, vh = self.volume_slider.rect
            vol_val = max(0.0, min(1.0, self.volume_slider.value))

            # Background track (175, 207, 70, 10)
            self.draw_3slice(cr, main_surf, vx, vy, vw, vh, 175, 207, 70, 10, 5, 5)

            # Filled track (175, 194, 70, 10)
            v_fill_w = int(vw * vol_val)
            if v_fill_w > 0:
                self.draw_3slice(cr, main_surf, vx, vy, v_fill_w, vh, 175, 194, 70, 10, 5, 5)

            # Thumb knob (85, 239, 11, 10)
            vt_x = vx + int(vw * vol_val) - 5
            vol_thumb_offset = 14 * self.volume_slider.state
            cr.save()
            cr.rectangle(vt_x, vy, 11, 10)
            cr.clip()
            cr.set_source_surface(main_surf, vt_x - (85 + vol_thumb_offset), vy - 239)
            cr.paint()
            cr.restore()

        # 4. Lower Strip: Transport Buttons
        transport = [
            self.btn_play,
            self.btn_pause,
            self.btn_stop,
            self.btn_prev,
            self.btn_next,
            self.btn_open
        ]
        for btn in transport:
            if btn == self.btn_play and is_playing:
                continue
            if btn == self.btn_pause and not is_playing:
                continue

            bx, by, bw, bh = btn.rect
            src_x = btn.img_left + (btn.state * btn.img_width)
            src_y = btn.img_top
            cr.save()
            cr.rectangle(bx, by, bw, bh)
            cr.clip()
            cr.set_source_surface(main_surf, bx - src_x, by - src_y)
            cr.paint()
            cr.restore()

        # 5. Lower Strip: Time Labels (Sans 11pt)
        time_base_y = lower_y + (lower_h // 2) + 4

        cr.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
        cr.set_font_size(11.0)

        # Current time
        cr.set_source_rgb(0.86, 0.86, 0.88)
        cr.move_to(time_x, time_base_y)
        cr.show_text(curr_str)

        # Slash separator
        slash_x = time_x + curr_ext.x_advance + 4
        cr.set_source_rgb(0.50, 0.50, 0.54)
        cr.move_to(slash_x, time_base_y)
        cr.show_text("/")

        # Total time
        tot_x = slash_x + slash_ext.x_advance + 4
        cr.set_source_rgb(0.66, 0.66, 0.70)
        cr.move_to(tot_x, time_base_y)
        cr.show_text(total_str)

        # 6. Lower Strip: Dynamic Media Badges
        if media_info:
            hw_active = media_info.get("hwdec") in ("auto", "vaapi", "vdpau", "nvdec", "drm", True)
            self.badge_hw.label_text = "HW" if hw_active else "SW"
            self.badge_hw.active = hw_active

            hdr_active = bool(media_info.get("hdr", False))
            self.badge_hdr.label_text = "HDR"
            self.badge_hdr.active = hdr_active

            v_raw = media_info.get("video_codec", "")
            if v_raw:
                self.badge_video.label_text = clean_codec_name(v_raw)

            a_raw = media_info.get("audio_codec", "")
            if a_raw:
                self.badge_audio.label_text = clean_codec_name(a_raw)

            chans = media_info.get("audio_channels", 2)
            if chans:
                self.badge_channel.label_text = f"{chans}.0" if chans in (1, 2) else f"{chans}"

        for badge in self.badges:
            bx, by, bw, bh = badge.rect
            if bx < 0 or bw <= 0:
                continue

            # Draw 3-slice pill background (485, 34, 41, 14)
            self.draw_3slice(cr, main_surf, bx, by, bw, bh, 485, 34, 41, 14, 3, 3)

            # Draw centered badge text
            cr.select_font_face("Tahoma", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
            cr.set_font_size(9.5)
            text = badge.label_text or ""
            text_ext = cr.text_extents(text)

            # Badge color: Amber/Gold for active HW, Cyan for active HDR, crisp grey for codecs
            if badge == self.badge_hw and getattr(badge, "active", False):
                cr.set_source_rgb(0.96, 0.77, 0.15)  # Amber gold
            elif badge == self.badge_hdr and getattr(badge, "active", False):
                cr.set_source_rgb(0.22, 0.74, 0.97)  # Light cyan
            elif badge.state == 1:
                cr.set_source_rgb(1.0, 1.0, 1.0)     # Hover white
            else:
                cr.set_source_rgb(0.78, 0.78, 0.82)  # Normal crisp silver

            tx = bx + (bw - text_ext.width) / 2 - text_ext.x_bearing
            ty = by + (bh - text_ext.height) / 2 - text_ext.y_bearing
            cr.move_to(tx, ty)
            cr.show_text(text)

        # 7. Lower Strip: Right Tool Buttons (Fullscreen, Control Box, Playlist, Stream)
        for btn in [self.btn_fullscreen, self.btn_stream, self.btn_playlist, self.btn_control_box]:
            bx, by, bw, bh = btn.rect
            if bx < 0:
                continue
            src_x = btn.img_left + (btn.state * btn.img_width)
            src_y = btn.img_top
            cr.save()
            cr.rectangle(bx, by, bw, bh)
            cr.clip()
            cr.set_source_surface(main_surf, bx - src_x, by - src_y)
            cr.paint()
            cr.restore()
        cr.restore()

    def _format_time(self, seconds: Optional[float], total_duration: Optional[float] = None) -> str:
        if seconds is None or math.isnan(seconds) or math.isinf(seconds):
            seconds = 0.0
        s = int(max(0.0, seconds))
        hrs = s // 3600
        mins = (s % 3600) // 60
        secs = s % 60
        force_hours = (total_duration is not None and not math.isnan(total_duration) and not math.isinf(total_duration) and total_duration >= 3600)
        if hrs > 0 or force_hours:
            return f"{hrs:02d}:{mins:02d}:{secs:02d}"
        return f"{mins:02d}:{secs:02d}"

    def hit_test(self, x: int, y: int, is_playing: bool = False) -> Optional[Any]:
        """
        Returns button or slider element under cursor coordinates.
        Prioritizes sliders with expanded vertical hit-box, then buttons, then badges.
        Respects playback state so play/pause overlapping buttons are correctly distinguished.
        """
        if self.scale_factor != 1.0 and self.scale_factor > 0:
            x = int(x / self.scale_factor)
            y = int(y / self.scale_factor)
        # Timebar slider hit-test with padding
        if self.timebar:
            tx, ty, tw, th = self.timebar.rect
            if tx <= x <= tx + tw and ty - 3 <= y <= ty + th + 4:
                return self.timebar

        # Volume slider hit-test with padding
        if self.volume_slider:
            vx, vy, vw, vh = self.volume_slider.rect
            if vx <= x <= vx + vw and vy - 3 <= y <= vy + vh + 4:
                return self.volume_slider

        # Transport & Right buttons (includes btn_mute in self.buttons)
        for btn in self.buttons:
            if btn == self.btn_play and is_playing:
                continue
            if btn == self.btn_pause and not is_playing:
                continue
            bx, by, bw, bh = btn.rect
            if bx <= x <= bx + bw and by <= y <= by + bh:
                return btn

        # Badges
        for badge in self.badges:
            bx, by, bw, bh = badge.rect
            if bx > 0 and bx <= x <= bx + bw and by <= y <= by + bh:
                return badge

        return None
