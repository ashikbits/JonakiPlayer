# SPDX-License-Identifier: GPL-3.0-or-later
"""
Jonaki for Linux - Main Player Window & Input Coordinator
Integrates MPV rendering surface, DSF skin overlay, keyboard shortcuts, and dialogs.
"""

import os
import sys
import time
import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
from gi.repository import Gtk, Gdk, GLib
import cairo
from typing import Optional, List, Dict, Any

from core.engine import JonakiCore, PotPlayerCore, PlaybackState
from core.media_db import MediaDatabase
from core.mpris import MPRIS2Service
from ui.skin_engine import PotSkinEngine
from ui.osd_overlay import OSDOverlay
from ui.context_menu import PotContextMenu
from ui.control_box import ControlBoxDialog
from ui.playlist_view import PlaylistWindow
from ui.media_info_dialog import MediaInfoDialog
from ui.subtitle_search_dialog import SubtitleSearchDialog
from audio.equalizer import EqualizerModel
from audio.dsp_chain import AudioDSPChain
from video.shader_manager import VideoShaderManager
from video.capture import MediaCaptureManager
from subtitle.subtitle_manager import SubtitleManager
from subtitle.translator import SubtitleTranslator


class JonakiMainWindow(Gtk.Window):
    def __init__(self, initial_files: Optional[List[str]] = None, config_preset: str = "Default"):
        super().__init__(title="Jonaki")
        self.set_default_size(960, 580)
        self.set_position(Gtk.WindowPosition.CENTER)

        # Set RGBA visual for true alpha channel transparency over OpenGL
        screen = self.get_screen()
        rgba = screen.get_rgba_visual() if screen else None
        if rgba:
            self.set_visual(rgba)

        # Subsystems
        self.db = MediaDatabase()
        self.equalizer = EqualizerModel()
        self.dsp = AudioDSPChain()
        self.shader_mgr = VideoShaderManager()
        self.capture_mgr = MediaCaptureManager()
        self.sub_mgr = SubtitleManager()
        self.translator = SubtitleTranslator()
        self.skin = PotSkinEngine()
        self.osd = OSDOverlay()

        # Playback playlist queue
        self.playlist: List[Dict[str, Any]] = []
        self.current_index: int = -1
        self.is_fullscreen: bool = False
        self._last_mouse_move_time = time.time()
        self._controls_visible = True
        self._pending_playback: Optional[Any] = None

        # Root vertical layout box
        self.main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add(self.main_box)

        # Core Playback Engine (libmpv C-FFI)
        self.core = JonakiCore()
        self.core.on_time_update = self._on_core_time_update
        self.core.on_state_change = self._on_core_state_change
        self.core.on_file_end = self._on_core_file_end

        # Route OSD messages to native GPU engine during active playback
        orig_show_osd = self.osd.show_osd
        def _show_osd_wrapper(text: str, duration_sec: float = 2.0):
            orig_show_osd(text, duration_sec)
            if self.core.state == PlaybackState.PLAYING:
                clean = text.replace('"', '\\"')
                self.core.command(f'show-text "{clean}" {int(duration_sec * 1000)}')
        self.osd.show_osd = _show_osd_wrapper

        # Video Surface with Overlay (Gtk.Overlay)
        self.video_overlay = Gtk.Overlay()

        self.video_area = Gtk.DrawingArea()
        self.video_area.set_can_focus(True)
        self.video_area.connect("realize", self._on_video_realize)
        self.video_overlay.add(self.video_area)

        # Cairo overlay layer for logo and OSD text / Tab Tech HUD
        self.osd_layer = Gtk.DrawingArea()
        if rgba:
            self.osd_layer.set_visual(rgba)
        self.osd_layer.set_app_paintable(True)
        self.osd_layer.connect("draw", self._on_draw_video_area)
        self.video_overlay.add_overlay(self.osd_layer)
        self.video_overlay.set_overlay_pass_through(self.osd_layer, True)

        self.video_overlay.add_events(Gdk.EventMask.BUTTON_PRESS_MASK |
                                      Gdk.EventMask.BUTTON_RELEASE_MASK |
                                      Gdk.EventMask.POINTER_MOTION_MASK |
                                      Gdk.EventMask.SCROLL_MASK |
                                      Gdk.EventMask.KEY_PRESS_MASK)
        self.video_overlay.connect("button-press-event", self._on_video_button_press)
        self.video_overlay.connect("scroll-event", self._on_video_scroll)
        self.video_overlay.connect("motion-notify-event", self._on_mouse_motion)
        self.main_box.pack_start(self.video_overlay, True, True, 0)

        # Bottom Skin Control Bar Area (62px: 22px upper slider strip + 40px lower button strip)
        self.skin_area = Gtk.DrawingArea()
        self.skin_area.set_size_request(-1, 62)
        self.skin_area.connect("draw", self._on_draw_skin_area)
        self.skin_area.add_events(Gdk.EventMask.BUTTON_PRESS_MASK |
                                 Gdk.EventMask.BUTTON_RELEASE_MASK |
                                 Gdk.EventMask.POINTER_MOTION_MASK)
        self.skin_area.connect("button-press-event", self._on_skin_button_press)
        self.skin_area.connect("button-release-event", self._on_skin_button_release)
        self.skin_area.connect("motion-notify-event", self._on_skin_motion)
        self.main_box.pack_end(self.skin_area, False, False, 0)

        # Right-click context menu
        self.context_menu = PotContextMenu(self.handle_command)

        # Secondary Windows
        self.control_box = ControlBoxDialog(self)
        self.playlist_window = PlaylistWindow(self)
        self.media_info_dialog = MediaInfoDialog(self)

        # Window events
        self.connect("key-press-event", self._on_key_press)
        self.connect("destroy", self._on_destroy)

        # Drag and Drop support
        self.drag_dest_set(Gtk.DestDefaults.ALL, [], Gdk.DragAction.COPY)
        self.drag_dest_add_uri_targets()
        self.connect("drag-data-received", self._on_drag_data_received)

        # MPRIS2 D-Bus Service for Desktop Integration
        self.mpris = MPRIS2Service(self)
        self.mpris.start()

        # Periodic timer for UI refresh & auto-hide controls
        GLib.timeout_add(100, self._on_ui_tick)

        if initial_files:
            self.add_files_to_playlist(initial_files, auto_play=True)

    def _on_video_realize(self, widget):
        # Obtain native X11 Window ID to attach in-process mpv
        gdk_win = widget.get_window()
        wid = None
        try:
            wid = gdk_win.get_xid()
        except Exception:
            pass

        if wid is None:
            try:
                top = widget.get_toplevel().get_window()
                if top:
                    wid = top.get_xid()
            except Exception:
                pass

        if wid is not None:
            self.core.set_wid(wid)

        self.apply_audio_filters()

        if getattr(self, "_pending_playback", None):
            fp, pts = self._pending_playback
            self._pending_playback = None
            self.play_file(fp, seek_pts=pts)
        elif len(self.playlist) > 0 and self.current_index >= 0:
            self.play_index(self.current_index)

    def _on_drag_data_received(self, widget, context, x, y, data, info, time_val):
        uris = data.get_uris()
        if not uris:
            context.finish(False, False, time_val)
            return

        from urllib.parse import unquote
        files = []
        for uri in uris:
            if uri.startswith("file://"):
                path = unquote(uri[7:])
                if os.path.exists(path):
                    files.append(path)
            elif uri.startswith("http://") or uri.startswith("https://"):
                files.append(uri)

        if files:
            sub_exts = ('.srt', '.ass', '.ssa', '.vtt', '.smi', '.sub')
            subs = [f for f in files if f.lower().endswith(sub_exts)]
            media = [f for f in files if not f.lower().endswith(sub_exts)]
            if subs:
                for s in subs:
                    self.core.load_subtitle(s)
                    self.osd.show_osd(f"Subtitle: {os.path.basename(s)}")
            if media:
                self.add_files_to_playlist(media, auto_play=True, clear_existing=True)
            context.finish(True, False, time_val)
        else:
            context.finish(False, False, time_val)

    def _on_ui_tick(self) -> bool:
        self.skin_area.queue_draw()

        # Dynamic overlay layer visibility: Hide when inactive to eliminate compositor Z-fighting & subtitle flickering
        has_osd = bool(self.osd.message and time.time() < self.osd.message_expire_time)
        has_hud = bool(self.osd.show_tech_info)
        has_sub = bool(self.osd.translated_sub and time.time() < self.osd.translated_sub_expire)
        is_idle = bool(self.core.state in (PlaybackState.IDLE, PlaybackState.STOPPED) and not self.core.current_file)

        # Real-time AI Subtitle Translation Worker
        if getattr(self.sub_mgr, "translation_enabled", False) and self.core.state == PlaybackState.PLAYING:
            sub_text = (self.core.get_property("sub-text") or "").strip()
            if sub_text and sub_text != getattr(self, "_last_sub_text", ""):
                self._last_sub_text = sub_text
                import threading
                def _trans_worker(txt=sub_text, dst=self.sub_mgr.target_language):
                    tr = self.translator.translate(txt, dst_lang=dst)
                    GLib.idle_add(self.osd.set_translated_sub, tr, 4.0)
                threading.Thread(target=_trans_worker, daemon=True).start()
            elif not sub_text and getattr(self, "_last_sub_text", ""):
                self._last_sub_text = ""

        # Dynamic overlay layer visibility: Only display osd_layer when idle (for logo)
        # or when Tab Tech HUD or translated subtitle is requested.
        # Transient OSD messages during playback are rendered natively via mpv show-text.
        show_overlay = has_hud or has_sub or is_idle or (has_osd and is_idle)
        if show_overlay:
            if not self.osd_layer.get_visible():
                self.osd_layer.show()
            self.osd_layer.queue_draw()
        else:
            if self.osd_layer.get_visible():
                self.osd_layer.hide()

        # Check auto-hide controls during fullscreen playback
        if self.is_fullscreen and self.core.state == PlaybackState.PLAYING:
            if time.time() - self._last_mouse_move_time > 2.5:
                if self._controls_visible:
                    self.skin_area.hide()
                    self._controls_visible = False
                    # Hide cursor
                    gdk_win = self.get_window()
                    if gdk_win:
                        gdk_win.set_cursor(Gdk.Cursor.new_for_display(Gdk.Display.get_default(), Gdk.CursorType.BLANK_CURSOR))
        return True

    # --- Draw Handlers ---

    def _on_draw_video_area(self, widget, cr: cairo.Context):
        alloc = widget.get_allocation()
        w, h = alloc.width, alloc.height

        # Always clear overlay background to 100% transparent alpha first
        cr.save()
        cr.set_operator(cairo.OPERATOR_CLEAR)
        cr.paint()
        cr.restore()

        # If no video is playing and no file loaded, draw PotPlayer logo background
        if self.core.state in (PlaybackState.IDLE, PlaybackState.STOPPED) and not self.core.current_file:
            cr.set_source_rgb(0.08, 0.08, 0.09)
            cr.rectangle(0, 0, w, h)
            cr.fill()

            logo_surf = self.skin.surfaces.get("Jonaki.png") or self.skin.surfaces.get("PotPlayer.png") or self.skin.surfaces.get("Main.png")
            cr.select_font_face("Segoe UI", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
            cr.set_font_size(24.0)
            cr.set_source_rgb(0.4, 0.4, 0.45)
            text = "Jonaki"
            ext = cr.text_extents(text)
            cr.move_to((w - ext.width) / 2, (h / 2) + 10)
            cr.show_text(text)

        # Draw OSD notifications and Tab Technical Info HUD
        info = {
            "file_path": self.core.current_file or "None",
            "video_codec": self.core.video_codec or "Auto",
            "audio_codec": self.core.audio_codec or "Auto",
            "hwdec": self.core.hwdec_active,
            "width": self.core.video_width if self.core.video_width > 0 else 1920,
            "height": self.core.video_height if self.core.video_height > 0 else 1080,
            "aspect": self.core.video_aspect or "16:9",
            "fps": self.core.video_fps if self.core.video_fps > 0 else 60.0
        }
        self.osd.render(cr, w, h, info, self.core.position, self.core.duration)

    def _on_draw_skin_area(self, widget, cr: cairo.Context):
        alloc = widget.get_allocation()
        w, h = alloc.width, alloc.height
        is_playing = (self.core.state == PlaybackState.PLAYING)
        bms = [b["timestamp"] for b in self.db.get_bookmarks(self.core.current_file or "")]

        media_info = {
            "hwdec": self.core.hwdec_active,
            "hdr": self.core.hdr_active,
            "video_codec": self.core.video_codec,
            "audio_codec": self.core.audio_codec,
            "audio_channels": self.core.audio_channels,
            "is_muted": self.core.is_muted
        }

        self.skin.render(cr, w, h, is_playing=is_playing,
                         position_sec=self.core.position, duration_sec=self.core.duration,
                         repeat_a=self.core.repeat_a, repeat_b=self.core.repeat_b,
                         bookmarks=bms, media_info=media_info)

    # --- Mouse & Interaction Handlers ---

    def _on_mouse_motion(self, widget, event):
        self._last_mouse_move_time = time.time()
        if not self._controls_visible:
            self.skin_area.show()
            self._controls_visible = True
            gdk_win = self.get_window()
            if gdk_win:
                gdk_win.set_cursor(None)

    def _on_video_button_press(self, widget, event):
        self.video_area.grab_focus()
        if event.button == 1:
            if event.type == Gdk.EventType._2BUTTON_PRESS:
                self.toggle_fullscreen()
            else:
                self.core.play_pause()
        elif event.button == 3:
            self.context_menu.popup(event, self.core)

    def _on_video_scroll(self, widget, event):
        if event.direction == Gdk.ScrollDirection.UP:
            self.core.adjust_volume(+2.0)
            self.osd.show_osd(f"Volume: {int(self.core.volume)}%")
        elif event.direction == Gdk.ScrollDirection.DOWN:
            self.core.adjust_volume(-2.0)
            self.osd.show_osd(f"Volume: {int(self.core.volume)}%")

    def _on_skin_button_press(self, widget, event):
        hit = self.skin.hit_test(int(event.x), int(event.y))
        if hit:
            if hit == self.skin.timebar:
                self.skin.timebar.is_dragging = True
                self.skin.timebar.state = 2  # Down
                tx, ty, tw, th = self.skin.timebar.rect
                ratio = max(0.0, min(1.0, (event.x - tx) / tw))
                self.core.seek_percent(ratio * 100.0)
            elif hit == self.skin.volume_slider:
                self.skin.volume_slider.is_dragging = True
                self.skin.volume_slider.state = 2  # Down
                vx, vy, vw, vh = self.skin.volume_slider.rect
                ratio = max(0.0, min(1.0, (event.x - vx) / vw))
                self.core.set_volume(ratio * 100.0)
            elif hasattr(hit, "cmd_id"):
                hit.state = 2  # Pressed
                self.handle_command(hit.cmd_id)
        self.skin_area.queue_draw()

    def _on_skin_button_release(self, widget, event):
        if self.skin.timebar:
            self.skin.timebar.is_dragging = False
            self.skin.timebar.state = 0
        if self.skin.volume_slider:
            self.skin.volume_slider.is_dragging = False
            self.skin.volume_slider.state = 0
        for btn in self.skin.buttons + self.skin.badges:
            btn.state = 0
        self.skin_area.queue_draw()

    def _on_skin_motion(self, widget, event):
        x, y = int(event.x), int(event.y)
        if self.skin.timebar and self.skin.timebar.is_dragging:
            tx, ty, tw, th = self.skin.timebar.rect
            ratio = max(0.0, min(1.0, (x - tx) / tw))
            self.core.seek_percent(ratio * 100.0)
        elif self.skin.volume_slider and self.skin.volume_slider.is_dragging:
            vx, vy, vw, vh = self.skin.volume_slider.rect
            ratio = max(0.0, min(1.0, (x - vx) / vw))
            self.core.set_volume(ratio * 100.0)
        else:
            if self.skin.timebar:
                tx, ty, tw, th = self.skin.timebar.rect
                self.skin.timebar.state = 1 if (tx <= x <= tx + tw and ty - 3 <= y <= ty + th + 4) else 0
            if self.skin.volume_slider:
                vx, vy, vw, vh = self.skin.volume_slider.rect
                self.skin.volume_slider.state = 1 if (vx <= x <= vx + vw and vy - 3 <= y <= vy + vh + 4) else 0
            for btn in self.skin.buttons + self.skin.badges:
                bx, by, bw, bh = btn.rect
                if bx <= x <= bx + bw and by <= y <= by + bh:
                    btn.state = 1  # Hover
                else:
                    btn.state = 0
        self.skin_area.queue_draw()

    # --- Keyboard Shortcut Dispatcher ---

    def _on_key_press(self, widget, event):
        keyval = event.keyval
        state = event.state

        ctrl = bool(state & Gdk.ModifierType.CONTROL_MASK)
        alt = bool(state & Gdk.ModifierType.MOD1_MASK)
        shift = bool(state & Gdk.ModifierType.SHIFT_MASK)

        # Open Files, URLs, Folders, Clipboard: Ctrl+O, F3, Ctrl+U, Ctrl+V, F2
        if (ctrl and keyval in (Gdk.KEY_o, Gdk.KEY_O) and not alt) or keyval == Gdk.KEY_F3:
            self._open_file_dialog()
            return True
        if ctrl and keyval in (Gdk.KEY_u, Gdk.KEY_U):
            self._open_url_dialog()
            return True
        if ctrl and keyval in (Gdk.KEY_v, Gdk.KEY_V) and not alt:
            self._open_from_clipboard()
            return True
        if keyval == Gdk.KEY_F2:
            self._open_folder_dialog()
            return True

        # Space: Play/Pause
        if keyval == Gdk.KEY_space:
            self.core.play_pause()
            return True

        # Enter: Fullscreen / Ctrl+Enter: Stretch Video (Fit Window/Screen)
        if keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            if ctrl:
                mode_str = self.core.toggle_stretch()
                self.osd.show_osd(f"Video Fit: {mode_str}")
            else:
                self.toggle_fullscreen()
            return True

        # Left / Right Seeks
        if keyval in (Gdk.KEY_Left, Gdk.KEY_KP_Left):
            if ctrl and alt:
                self.core.seek_relative(-300.0)
                self.osd.show_osd("Seek: -5 min")
            elif shift:
                self.core.seek_relative(-60.0)
                self.osd.show_osd("Seek: -1 min")
            elif ctrl:
                self.core.seek_relative(-30.0)
                self.osd.show_osd("Seek: -30 sec")
            else:
                self.core.seek_relative(-5.0)
                self.osd.show_osd("Seek: -5 sec")
            return True

        if keyval in (Gdk.KEY_Right, Gdk.KEY_KP_Right):
            if ctrl and alt:
                self.core.seek_relative(+300.0)
                self.osd.show_osd("Seek: +5 min")
            elif shift:
                self.core.seek_relative(+60.0)
                self.osd.show_osd("Seek: +1 min")
            elif ctrl:
                self.core.seek_relative(+30.0)
                self.osd.show_osd("Seek: +30 sec")
            else:
                self.core.seek_relative(+5.0)
                self.osd.show_osd("Seek: +5 sec")
            return True

        # Up / Down Volume & Shift+Up/Down Volume Boost (PreAmp)
        if keyval in (Gdk.KEY_Up, Gdk.KEY_KP_Up):
            if shift:
                self.dsp.audio_boost_db = min(12.0, self.dsp.audio_boost_db + 1.0)
                self.apply_audio_filters()
                self.osd.show_osd(f"Audio Boost PreAmp: +{self.dsp.audio_boost_db:.1f} dB")
            else:
                self.core.adjust_volume(+2.0)
                self.osd.show_osd(f"Volume: {int(self.core.volume)}%")
            return True

        if keyval in (Gdk.KEY_Down, Gdk.KEY_KP_Down):
            if shift:
                self.dsp.audio_boost_db = max(0.0, self.dsp.audio_boost_db - 1.0)
                self.apply_audio_filters()
                self.osd.show_osd(f"Audio Boost PreAmp: +{self.dsp.audio_boost_db:.1f} dB")
            else:
                self.core.adjust_volume(-2.0)
                self.osd.show_osd(f"Volume: {int(self.core.volume)}%")
            return True

        # Shift+N: Toggle Normalizer (Auto Volume Control)
        if shift and keyval in (Gdk.KEY_n, Gdk.KEY_N):
            self.dsp.normalizer_enabled = not self.dsp.normalizer_enabled
            self.apply_audio_filters()
            self.osd.show_osd(f"Auto Volume Control (Normalizer): {'ON' if self.dsp.normalizer_enabled else 'OFF'}")
            return True

        # Audio Track & Audio Sync
        if keyval in (Gdk.KEY_a, Gdk.KEY_A) and not ctrl:
            self.core.cycle_audio_track()
            self.osd.show_osd("Audio Track Cycled")
            return True
        if shift and keyval == Gdk.KEY_bracketleft:
            self.core.set_audio_delay(-0.05)
            self.osd.show_osd("Audio Sync: -50 ms")
            return True
        if shift and keyval == Gdk.KEY_bracketright:
            self.core.set_audio_delay(+0.05)
            self.osd.show_osd("Audio Sync: +50 ms")
            return True
        if shift and keyval == Gdk.KEY_backslash:
            self.core.set_audio_delay(0.0)
            self.osd.show_osd("Audio Sync: 0.0s (Reset)")
            return True

        # Subtitles: S (Cycle Primary), Shift+S (Cycle Secondary), Alt+O (Open), Alt+H (Visibility), Alt+Left/Right (Sync), Alt+PgUp/PgDn (Size), Alt+Up/Down (Pos)
        if keyval in (Gdk.KEY_s, Gdk.KEY_S) and not (ctrl or alt):
            if shift:
                self.core.cycle_secondary_subtitle_track()
                sec_id = self.core.get_current_secondary_subtitle_track_id()
                self.osd.show_osd(f"Secondary Subtitle Track: {sec_id or 'Off'}")
            else:
                self.core.cycle_subtitle_track()
                self.osd.show_osd("Subtitle Track Cycled")
            return True
        if alt and keyval in (Gdk.KEY_o, Gdk.KEY_O):
            self._open_subtitle_dialog()
            return True
        if alt and keyval in (Gdk.KEY_h, Gdk.KEY_H):
            vis = self.sub_mgr.toggle_visibility()
            self.core.set_subtitle_visibility(vis)
            self.osd.show_osd(f"Subtitles: {'Show' if vis else 'Hide'}")
            return True
        if alt and keyval in (Gdk.KEY_Left, Gdk.KEY_KP_Left):
            offset = self.sub_mgr.adjust_sync(-0.5)
            self.core.set_subtitle_delay(offset)
            self.osd.show_osd(f"Subtitle Sync: {offset:+.1f}s")
            return True
        if alt and keyval in (Gdk.KEY_Right, Gdk.KEY_KP_Right):
            offset = self.sub_mgr.adjust_sync(+0.5)
            self.core.set_subtitle_delay(offset)
            self.osd.show_osd(f"Subtitle Sync: {offset:+.1f}s")
            return True
        if alt and keyval == Gdk.KEY_slash:
            self.sub_mgr.reset_sync()
            self.core.set_subtitle_delay(0.0)
            self.osd.show_osd("Subtitle Sync: 0.0s (Reset)")
            return True
        if alt and keyval in (Gdk.KEY_Page_Up, Gdk.KEY_KP_Page_Up):
            sz = self.sub_mgr.increase_font_size(2)
            self.core.set_subtitle_font_size(sz)
            self.osd.show_osd(f"Subtitle Size: {sz} pt")
            return True
        if alt and keyval in (Gdk.KEY_Page_Down, Gdk.KEY_KP_Page_Down):
            sz = self.sub_mgr.decrease_font_size(2)
            self.core.set_subtitle_font_size(sz)
            self.osd.show_osd(f"Subtitle Size: {sz} pt")
            return True
        if not (ctrl or alt or shift) and keyval in (Gdk.KEY_Page_Down, Gdk.KEY_KP_Page_Down):
            self.play_next()
            return True
        if not (ctrl or alt or shift) and keyval in (Gdk.KEY_Page_Up, Gdk.KEY_KP_Page_Up):
            self.play_prev()
            return True
        if alt and keyval in (Gdk.KEY_Up, Gdk.KEY_KP_Up):
            pos = self.core.adjust_subtitle_pos(-2)
            self.osd.show_osd(f"Subtitle Position: {pos}%")
            return True
        if alt and keyval in (Gdk.KEY_Down, Gdk.KEY_KP_Down):
            pos = self.core.adjust_subtitle_pos(+2)
            self.osd.show_osd(f"Subtitle Position: {pos}%")
            return True
        if alt and keyval in (Gdk.KEY_Home, Gdk.KEY_KP_Home):
            self.core.set_property("sub-pos", "100")
            self.core.sub_pos = 100
            self.osd.show_osd("Subtitle Position: Default (100%)")
            return True
        if alt and keyval in (Gdk.KEY_t, Gdk.KEY_T):
            self.sub_mgr.translation_enabled = not self.sub_mgr.translation_enabled
            self.osd.show_osd(f"AI Subtitle Translation: {'ON' if self.sub_mgr.translation_enabled else 'OFF'}")
            return True

        # Video Processing Shortcuts
        # V: Cycle Aspect Ratio
        if keyval in (Gdk.KEY_v, Gdk.KEY_V):
            mode_str = self.core.cycle_aspect_ratio()
            self.osd.show_osd(f"Aspect Ratio: {mode_str}")
            return True
        # Ctrl+B: Deband Filter
        if ctrl and keyval in (Gdk.KEY_b, Gdk.KEY_B):
            self.core.toggle_deband()
            self.osd.show_osd("Deband Filter Toggled")
            return True
        # Alt+K: Rotate Video 90 deg
        if alt and keyval in (Gdk.KEY_k, Gdk.KEY_K):
            rot_str = self.core.rotate_video()
            self.osd.show_osd(f"Video Rotation: {rot_str}")
            return True
        # Frame Step Forward: D or '.' / Frame Step Backward: F or ','
        if ((keyval in (Gdk.KEY_d, Gdk.KEY_D) and not ctrl) or
            keyval in (Gdk.KEY_period, Gdk.KEY_greater)):
            self.core.step_frame_forward()
            self.osd.show_osd("Frame Step +1")
            return True
        if ((keyval in (Gdk.KEY_f, Gdk.KEY_F) and not ctrl) or
            keyval in (Gdk.KEY_comma, Gdk.KEY_less)):
            self.core.step_frame_backward()
            self.osd.show_osd("Frame Step -1")
            return True

        # Video Flip: Ctrl+Z (Horizontal Flip), Ctrl+X (Vertical Flip)
        if ctrl and keyval in (Gdk.KEY_z, Gdk.KEY_Z) and not alt:
            active = self.core.toggle_horizontal_flip()
            self.osd.show_osd(f"Horizontal Flip (Mirror): {'ON' if active else 'OFF'}")
            return True
        if ctrl and keyval in (Gdk.KEY_x, Gdk.KEY_X) and not alt:
            active = self.core.toggle_vertical_flip()
            self.osd.show_osd(f"Vertical Flip (Invert): {'ON' if active else 'OFF'}")
            return True

        # Window Sizing & Stay On Top
        if ctrl and keyval in (Gdk.KEY_t, Gdk.KEY_T):
            is_top = not self.get_property("keep-above")
            self.set_keep_above(is_top)
            self.osd.show_osd(f"Stay on Top: {'ON' if is_top else 'OFF'}")
            return True
        if alt and keyval in (Gdk.KEY_1, Gdk.KEY_KP_1):
            w = int(self.core.video_width * 0.5) if self.core.video_width > 0 else 640
            h = int(self.core.video_height * 0.5 + 62) if self.core.video_height > 0 else 360
            self.resize(w, h)
            self.osd.show_osd("Window Size: 50% (0.5x)")
            return True
        if alt and keyval in (Gdk.KEY_2, Gdk.KEY_KP_2):
            w = self.core.video_width if self.core.video_width > 0 else 960
            h = (self.core.video_height + 62) if self.core.video_height > 0 else 580
            self.resize(w, h)
            self.osd.show_osd("Window Size: 100% (Original Size)")
            return True
        if alt and keyval in (Gdk.KEY_3, Gdk.KEY_KP_3):
            w = int(self.core.video_width * 1.5) if self.core.video_width > 0 else 1280
            h = int(self.core.video_height * 1.5 + 62) if self.core.video_height > 0 else 720
            self.resize(w, h)
            self.osd.show_osd("Window Size: 150% (1.5x)")
            return True
        if alt and keyval in (Gdk.KEY_4, Gdk.KEY_KP_4):
            w = int(self.core.video_width * 2.0) if self.core.video_width > 0 else 1920
            h = int(self.core.video_height * 2.0 + 62) if self.core.video_height > 0 else 1080
            self.resize(w, h)
            self.osd.show_osd("Window Size: 200% (2.0x)")
            return True

        # Escape: Exit fullscreen or stop playback
        if keyval == Gdk.KEY_Escape:
            if self.is_fullscreen:
                self.toggle_fullscreen()
            else:
                self.core.stop()
            return True

        # Mute
        if keyval in (Gdk.KEY_m, Gdk.KEY_M):
            self.core.toggle_mute()
            self.osd.show_osd("Mute: ON" if self.core.is_muted else "Mute: OFF")
            return True

        # Speed: Z, X, C (when not ctrl or alt)
        if keyval in (Gdk.KEY_z, Gdk.KEY_Z) and not (ctrl or alt):
            self.core.set_speed(1.0)
            self.osd.show_osd("Speed: 1.0x")
            return True
        if keyval in (Gdk.KEY_x, Gdk.KEY_X) and not (ctrl or alt):
            self.core.set_speed(self.core.speed - 0.1)
            self.osd.show_osd(f"Speed: {self.core.speed:.1f}x")
            return True
        if keyval in (Gdk.KEY_c, Gdk.KEY_C) and not (ctrl or alt):
            self.core.set_speed(self.core.speed + 0.1)
            self.osd.show_osd(f"Speed: {self.core.speed:.1f}x")
            return True

        # A-B Repeat: [, ], \
        if keyval == Gdk.KEY_bracketleft and not shift:
            self.set_repeat_a()
            return True
        if keyval == Gdk.KEY_bracketright and not shift:
            self.set_repeat_b()
            return True
        if keyval == Gdk.KEY_backslash:
            self.core.clear_repeat()
            self.osd.show_osd("A-B Repeat: Cleared")
            return True

        # Bookmarks: P (add), H (prev bookmark), J (next bookmark)
        if keyval in (Gdk.KEY_p, Gdk.KEY_P) and not ctrl:
            if self.core.current_file:
                self.db.add_bookmark(self.core.current_file, self.core.position)
                self.osd.show_osd(f"Bookmark Added: {self.skin._format_time(self.core.position)}")
            return True
        if keyval in (Gdk.KEY_h, Gdk.KEY_H) and not (ctrl or alt or shift):
            bms = self.db.get_bookmarks(self.core.current_file or "")
            if bms:
                prev_pts = [b["timestamp"] for b in bms if b["timestamp"] < self.core.position - 0.5]
                target = max(prev_pts) if prev_pts else bms[-1]["timestamp"]
                self.core.seek_absolute(target)
                self.osd.show_osd(f"Bookmark: {self.skin._format_time(target)}")
            return True
        if keyval in (Gdk.KEY_j, Gdk.KEY_J) and not (ctrl or alt or shift):
            bms = self.db.get_bookmarks(self.core.current_file or "")
            if bms:
                next_pts = [b["timestamp"] for b in bms if b["timestamp"] > self.core.position + 0.5]
                target = min(next_pts) if next_pts else bms[0]["timestamp"]
                self.core.seek_absolute(target)
                self.osd.show_osd(f"Bookmark: {self.skin._format_time(target)}")
            return True

        # Tab: Technical Info HUD
        if keyval == Gdk.KEY_Tab:
            self.osd.toggle_tech_info()
            self.video_area.queue_draw()
            return True

        # Function Keys: F1 (About / Ctrl+F1: Media Info), F4 (Close), F5 (Prefs), F6 (Control Box), F7 (Equalizer), F8/F12 (Playlist)
        if keyval == Gdk.KEY_F1:
            if ctrl:
                self.show_media_info_dialog()
            else:
                self.handle_command("CMD_ABOUT_DIALOG")
            return True
        if keyval == Gdk.KEY_F4:
            self.core.stop()
            return True
        if keyval == Gdk.KEY_F6:
            self.control_box.show_all()
            return True
        if keyval == Gdk.KEY_F7:
            self.control_box.show_all()
            # Switch to Audio tab
            return True
        if keyval in (Gdk.KEY_F8, Gdk.KEY_F12):
            self.playlist_window.show_all()
            return True

        # Capture: Ctrl+P, Ctrl+Alt+G (GIF), Ctrl+Alt+S (Storyboard)
        if ctrl and keyval in (Gdk.KEY_p, Gdk.KEY_P):
            self.handle_command("CMD_CAPTURE_FRAME")
            return True
        if ctrl and alt and keyval in (Gdk.KEY_g, Gdk.KEY_G):
            self.handle_command("CMD_CREATE_GIF")
            return True
        if ctrl and alt and keyval in (Gdk.KEY_s, Gdk.KEY_S):
            self.handle_command("CMD_CREATE_STORYBOARD")
            return True

        # Colors: Q (Reset), W/E (Brightness), R/T (Contrast), Y/U (Saturation), I/O (Hue)
        if keyval in (Gdk.KEY_q, Gdk.KEY_Q):
            self.shader_mgr.reset_colors()
            self.core.set_video_colors(0, 0, 0, 0, 0)
            self.osd.show_osd("Video Colors: Reset")
            return True
        if keyval in (Gdk.KEY_w, Gdk.KEY_W):
            self.shader_mgr.brightness = max(-100, self.shader_mgr.brightness - 1)
            self.core.set_video_colors(self.shader_mgr.brightness, self.shader_mgr.contrast, self.shader_mgr.saturation, self.shader_mgr.hue, 0)
            self.osd.show_osd(f"Brightness: {self.shader_mgr.brightness}%")
            return True
        if keyval in (Gdk.KEY_e, Gdk.KEY_E):
            self.shader_mgr.brightness = min(100, self.shader_mgr.brightness + 1)
            self.core.set_video_colors(self.shader_mgr.brightness, self.shader_mgr.contrast, self.shader_mgr.saturation, self.shader_mgr.hue, 0)
            self.osd.show_osd(f"Brightness: {self.shader_mgr.brightness}%")
            return True
        if keyval in (Gdk.KEY_r, Gdk.KEY_R):
            self.shader_mgr.contrast = max(-100, self.shader_mgr.contrast - 1)
            self.core.set_video_colors(self.shader_mgr.brightness, self.shader_mgr.contrast, self.shader_mgr.saturation, self.shader_mgr.hue, 0)
            self.osd.show_osd(f"Contrast: {self.shader_mgr.contrast}%")
            return True
        if keyval in (Gdk.KEY_t, Gdk.KEY_T) and not (ctrl or alt):
            self.shader_mgr.contrast = min(100, self.shader_mgr.contrast + 1)
            self.core.set_video_colors(self.shader_mgr.brightness, self.shader_mgr.contrast, self.shader_mgr.saturation, self.shader_mgr.hue, 0)
            self.osd.show_osd(f"Contrast: {self.shader_mgr.contrast}%")
            return True

        return False

    # --- Command Dispatcher ---

    def handle_command(self, cmd_id: str, arg: Any = None) -> None:
        if cmd_id in ("CMD_MEDIA_PLAY", "CMD_MEDIA_PAUSE", "CMD_MEDIA_PLAY_PAUSE"):
            self.core.play_pause()
        elif cmd_id == "CMD_MEDIA_CLOSE":
            self.core.stop()
        elif cmd_id == "ID_PLAYBACK_5SEC_BACK":
            self.core.seek_relative(-5.0)
            self.osd.show_osd("Seek: -5 sec")
        elif cmd_id == "ID_PLAYBACK_5SEC_FORW":
            self.core.seek_relative(+5.0)
            self.osd.show_osd("Seek: +5 sec")
        elif cmd_id in ("ID_BASE_OPEN", "CMD_OPEN_FILE"):
            self._open_file_dialog()
        elif cmd_id == "CMD_OPEN_CLIPBOARD":
            self._open_from_clipboard()
        elif cmd_id == "CMD_OPEN_FOLDER":
            self._open_folder_dialog()
        elif cmd_id == "CMD_OPEN_URL":
            self._open_url_dialog()
        elif cmd_id == "CMD_OPEN_SCREEN_CAPTURE":
            self.play_file("v4l2:///dev/video0")
            self.osd.show_osd("Screen Capture Device")
        elif cmd_id == "CMD_OPEN_WEBCAM":
            self.play_file("v4l2:///dev/video0")
            self.osd.show_osd("Webcam Device")
        elif cmd_id == "CMD_FULLSCREEN":
            self.toggle_fullscreen()
        elif cmd_id == "CMD_VIDEO_STRETCH":
            mode_str = self.core.toggle_stretch()
            self.osd.show_osd(f"Video Fit: {mode_str}")
        elif cmd_id in ("CMD_CONTROL_BOX", "ID_CONTROL_BOX_WINDOW", "CMD_PREFERENCES_DIALOG", "CMD_EQUALIZER_DIALOG"):
            self.control_box.show_all()
        elif cmd_id in ("CMD_PLAYLIST_WINDOW", "ID_PLAYLIST_WINDOW"):
            self.playlist_window.show_all()
        elif cmd_id == "CMD_POPUPMENU_STREAM_SELECT":
            self._open_url_dialog()
        elif cmd_id == "CMD_OSD_PLAYINFO":
            self.osd.toggle_tech_info()
            self.video_area.queue_draw()
        elif cmd_id in ("CMD_TOGGLE_HWDEC", "CMD_VIDEO_OUT_HW_SW_MESSAGE"):
            self.core.toggle_hwdec()
            self.osd.show_osd(f"Hardware Acceleration: {'ON (HW)' if self.core.hwdec_active != 'no' else 'OFF (SW)'}")
        elif cmd_id in ("ID_VIDEO_PS_SMPTE_2084", "CMD_TOGGLE_HDR"):
            self.core.toggle_hdr()
            self.osd.show_osd(f"HDR Tone-mapping: {'ON' if self.core.hdr_active else 'OFF'}")
        elif cmd_id == "CMD_DEINTERLACE_TOGGLE":
            self.core.toggle_deinterlace()
            self.osd.show_osd("Deinterlacing Toggled")
        elif cmd_id == "CMD_COLOR_RESET":
            self.shader_mgr.reset_colors()
            self.core.set_video_colors(0, 0, 0, 0, 0)
            self.osd.show_osd("Video Colors: Reset")
        elif cmd_id == "CMD_SHADER_SHARPEN":
            self.shader_mgr.enable_shader("sharpen.hook")
            self.osd.show_osd("Pixel Shader: Sharpen 3x3")
        elif cmd_id == "CMD_SHADER_ADAPTIVE_SHARPEN":
            self.shader_mgr.enable_shader("adaptive_sharpen.hook")
            self.osd.show_osd("Pixel Shader: Adaptive Sharpen")
        elif cmd_id == "CMD_SHADER_DENOISE":
            self.osd.show_osd("Pixel Shader: Denoise")
        elif cmd_id == "CMD_SHADER_CLEAR":
            self.shader_mgr.active_shaders.clear()
            self.osd.show_osd("Pixel Shaders: Cleared")
        elif cmd_id == "CMD_CYCLE_AUDIO_TRACK":
            self.core.cycle_audio_track()
            self.osd.show_osd("Audio Track Cycled")
        elif cmd_id in ("CMD_AUDIO_MUTE", "ID_AUDIO_MUTE"):
            self.core.toggle_mute()
            self.osd.show_osd("Mute: ON" if self.core.is_muted else "Mute: OFF")
        elif cmd_id == "CMD_AUDIO_NORMALIZER_TOGGLE":
            self.dsp.normalizer_enabled = not self.dsp.normalizer_enabled
            self.apply_audio_filters()
            self.osd.show_osd(f"Auto Volume Control: {'ON' if self.dsp.normalizer_enabled else 'OFF'}")
        elif cmd_id == "CMD_SUB_OPEN":
            self._open_subtitle_dialog()
        elif cmd_id == "CMD_SUB_VISIBILITY":
            vis = self.sub_mgr.toggle_visibility()
            self.core.set_subtitle_visibility(vis)
            self.osd.show_osd(f"Subtitles: {'Show' if vis else 'Hide'}")
        elif cmd_id == "CMD_CYCLE_SUB_TRACK":
            self.core.cycle_subtitle_track()
            self.osd.show_osd("Subtitle Track Cycled")
        elif cmd_id == "CMD_SUB_SYNC_MINUS_500":
            offset = self.sub_mgr.adjust_sync(-0.5)
            self.core.set_subtitle_delay(offset)
            self.osd.show_osd(f"Subtitle Sync: {offset:+.1f}s")
        elif cmd_id == "CMD_SUB_SYNC_PLUS_500":
            offset = self.sub_mgr.adjust_sync(+0.5)
            self.core.set_subtitle_delay(offset)
            self.osd.show_osd(f"Subtitle Sync: {offset:+.1f}s")
        elif cmd_id == "CMD_SUB_SYNC_RESET":
            self.sub_mgr.reset_sync()
            self.core.set_subtitle_delay(0.0)
            self.osd.show_osd("Subtitle Sync: 0.0s (Reset)")
        elif cmd_id == "CMD_SUB_TRANSLATE_TOGGLE":
            self.sub_mgr.translation_enabled = not self.sub_mgr.translation_enabled
            self.osd.show_osd(f"AI Subtitle Translation: {'ON' if self.sub_mgr.translation_enabled else 'OFF'}")
        elif cmd_id == "CMD_SUB_ONLINE_SEARCH":
            self.show_subtitle_search_dialog()
        elif cmd_id == "CMD_CAPTURE_FRAME":
            fn = self.capture_mgr.generate_capture_filename()
            if self.core.take_screenshot(fn):
                self.osd.show_osd(f"Snapshot Saved: {os.path.basename(fn)}")
        elif cmd_id == "CMD_CAPTURE_FRAME_AS":
            self._save_frame_as_dialog()
        elif cmd_id == "CMD_CAPTURE_TO_CLIPBOARD":
            fn = self.capture_mgr.generate_capture_filename()
            if self.core.take_screenshot(fn):
                self.capture_mgr.copy_file_to_clipboard(fn)
                self.osd.show_osd("Snapshot Copied to Clipboard")
        elif cmd_id == "CMD_CREATE_GIF":
            if self.core.current_file:
                gif_path = self.capture_mgr.create_animated_gif(self.core.current_file, self.core.position, 5.0)
                if gif_path:
                    self.osd.show_osd(f"GIF Created: {os.path.basename(gif_path)}")
        elif cmd_id == "CMD_CREATE_STORYBOARD":
            if self.core.current_file:
                sb_path = self.capture_mgr.create_storyboard(self.core.current_file, self.core.duration)
                if sb_path:
                    self.osd.show_osd(f"Storyboard Created: {os.path.basename(sb_path)}")
        elif cmd_id == "CMD_MEDIA_INFO_DIALOG":
            self.show_media_info_dialog()
        elif cmd_id == "CMD_SET_AUDIO_TRACK":
            self.core.set_audio_track(arg)
            self.osd.show_osd(f"Audio Track: {arg}")
        elif cmd_id == "CMD_SET_SUB_TRACK":
            self.core.set_subtitle_track(arg)
            self.osd.show_osd(f"Subtitle Track: {arg}")
        elif cmd_id == "CMD_SET_SECONDARY_SUB_TRACK":
            self.core.set_secondary_subtitle_track(arg)
            self.osd.show_osd(f"Secondary Subtitle Track: {arg}")
        elif cmd_id == "CMD_CYCLE_SECONDARY_SUB":
            self.core.cycle_secondary_subtitle_track()
            sec_id = self.core.get_current_secondary_subtitle_track_id()
            self.osd.show_osd(f"Secondary Subtitle Track: {sec_id or 'Off'}")
        elif cmd_id == "CMD_SET_ASPECT_RATIO":
            self.core.set_aspect_ratio_mode(str(arg))
            self.osd.show_osd(f"Aspect Ratio: {arg}")
        elif cmd_id == "CMD_VIDEO_HFLIP":
            act = self.core.toggle_horizontal_flip()
            self.osd.show_osd(f"Horizontal Flip: {'ON' if act else 'OFF'}")
        elif cmd_id == "CMD_VIDEO_VFLIP":
            act = self.core.toggle_vertical_flip()
            self.osd.show_osd(f"Vertical Flip: {'ON' if act else 'OFF'}")
        elif cmd_id == "CMD_VIDEO_ROTATE":
            rot = self.core.rotate_video()
            self.osd.show_osd(f"Video Rotation: {rot}")
        elif cmd_id == "CMD_VIDEO_RESET_ORIENTATION":
            self.core.reset_video_orientation()
            self.osd.show_osd("Video Orientation Reset")
        elif cmd_id == "CMD_DEBAND_TOGGLE":
            self.core.toggle_deband()
            self.osd.show_osd(f"Deband Filter: {'ON' if self.core.deband_active else 'OFF'}")
        elif cmd_id == "CMD_FRAME_STEP":
            self.core.step_frame_forward()
            self.osd.show_osd("Frame Step +1")
        elif cmd_id == "CMD_FRAME_BACK_STEP":
            self.core.step_frame_backward()
            self.osd.show_osd("Frame Step -1")
        elif cmd_id == "CMD_SPEED_NORMAL":
            self.core.set_speed(1.0)
            self.osd.show_osd("Speed: 1.0x")
        elif cmd_id == "CMD_SPEED_DOWN":
            self.core.set_speed(self.core.speed - 0.1)
            self.osd.show_osd(f"Speed: {self.core.speed:.1f}x")
        elif cmd_id == "CMD_SPEED_UP":
            self.core.set_speed(self.core.speed + 0.1)
            self.osd.show_osd(f"Speed: {self.core.speed:.1f}x")
        elif cmd_id == "CMD_AUDIO_BOOST_UP":
            self.dsp.audio_boost_db = min(24.0, self.dsp.audio_boost_db + 1.0)
            self.apply_audio_filters()
            self.osd.show_osd(f"Audio Boost PreAmp: +{self.dsp.audio_boost_db:.1f} dB")
        elif cmd_id == "CMD_AUDIO_BOOST_DOWN":
            self.dsp.audio_boost_db = max(0.0, self.dsp.audio_boost_db - 1.0)
            self.apply_audio_filters()
            self.osd.show_osd(f"Audio Boost PreAmp: +{self.dsp.audio_boost_db:.1f} dB")
        elif cmd_id == "CMD_AUDIO_SYNC_MINUS":
            self.core.set_audio_delay(self.core.audio_delay_sec - 0.05)
            self.osd.show_osd(f"Audio Sync: {self.core.audio_delay_sec*1000:+.0f} ms")
        elif cmd_id == "CMD_AUDIO_SYNC_PLUS":
            self.core.set_audio_delay(self.core.audio_delay_sec + 0.05)
            self.osd.show_osd(f"Audio Sync: {self.core.audio_delay_sec*1000:+.0f} ms")
        elif cmd_id == "CMD_AUDIO_SYNC_RESET":
            self.core.set_audio_delay(0.0)
            self.osd.show_osd("Audio Sync: 0.0s (Reset)")
        elif cmd_id == "CMD_SUB_POS_UP":
            pos = self.core.adjust_subtitle_pos(-2)
            self.osd.show_osd(f"Subtitle Position: {pos}%")
        elif cmd_id == "CMD_SUB_POS_DOWN":
            pos = self.core.adjust_subtitle_pos(+2)
            self.osd.show_osd(f"Subtitle Position: {pos}%")
        elif cmd_id == "CMD_SUB_POS_RESET":
            self.core.set_property("sub-pos", "100")
            self.core.sub_pos = 100
            self.osd.show_osd("Subtitle Position: Default (100%)")
        elif cmd_id == "CMD_SUB_SIZE_UP":
            sz = self.sub_mgr.increase_font_size(2)
            self.core.set_subtitle_font_size(sz)
            self.osd.show_osd(f"Subtitle Size: {sz} pt")
        elif cmd_id == "CMD_SUB_SIZE_DOWN":
            sz = self.sub_mgr.decrease_font_size(2)
            self.core.set_subtitle_font_size(sz)
            self.osd.show_osd(f"Subtitle Size: {sz} pt")
        elif cmd_id == "CMD_BOOKMARK_ADD":
            if self.core.current_file:
                self.db.add_bookmark(self.core.current_file, self.core.position)
                self.osd.show_osd(f"Bookmark Added: {self.skin._format_time(self.core.position)}")
                self.skin_area.queue_draw()
        elif cmd_id == "CMD_BOOKMARK_PREV":
            bms = self.db.get_bookmarks(self.core.current_file or "")
            if bms:
                prev_pts = [b["timestamp"] for b in bms if b["timestamp"] < self.core.position - 0.5]
                target = max(prev_pts) if prev_pts else bms[-1]["timestamp"]
                self.core.seek_absolute(target)
                self.osd.show_osd(f"Bookmark: {self.skin._format_time(target)}")
        elif cmd_id == "CMD_BOOKMARK_NEXT":
            bms = self.db.get_bookmarks(self.core.current_file or "")
            if bms:
                next_pts = [b["timestamp"] for b in bms if b["timestamp"] > self.core.position + 0.5]
                target = min(next_pts) if next_pts else bms[0]["timestamp"]
                self.core.seek_absolute(target)
                self.osd.show_osd(f"Bookmark: {self.skin._format_time(target)}")
        elif cmd_id == "CMD_BOOKMARK_CLEAR":
            if self.core.current_file:
                self.db.clear_bookmarks(self.core.current_file)
                self.osd.show_osd("Bookmarks Cleared")
                self.skin_area.queue_draw()
        elif cmd_id == "CMD_ABOUT_DIALOG":
            self._show_about_dialog()
        elif cmd_id == "CMD_APP_EXIT":
            self.close()

    def show_media_info_dialog(self) -> None:
        info = self.core.get_media_detailed_info()
        self.media_info_dialog.update_info(info)
        self.media_info_dialog.show_all()

    def show_subtitle_search_dialog(self) -> None:
        def _on_sub_downloaded(sub_path: str):
            self.core.load_subtitle(sub_path)
            self.osd.show_osd(f"Subtitle Loaded: {os.path.basename(sub_path)}")

        dialog = SubtitleSearchDialog(self, self.core.current_file, _on_sub_downloaded)
        dialog.show_all()

    def _save_frame_as_dialog(self) -> None:
        dialog = Gtk.FileChooserDialog(title="Save Frame As", parent=self,
                                       action=Gtk.FileChooserAction.SAVE)
        dialog.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_SAVE, Gtk.ResponseType.OK)
        dialog.set_current_name(f"Jonaki_{int(time.time())}.png")
        if dialog.run() == Gtk.ResponseType.OK:
            fn = dialog.get_filename()
            if fn:
                self.core.take_screenshot(fn)
                self.osd.show_osd(f"Snapshot Saved: {os.path.basename(fn)}")
        dialog.destroy()

    def toggle_fullscreen(self) -> None:
        if self.is_fullscreen:
            self.unfullscreen()
            self.is_fullscreen = False
            self.skin_area.show()
            self._controls_visible = True
        else:
            self.fullscreen()
            self.is_fullscreen = True

    # --- Core Event Callbacks ---

    def _on_core_time_update(self, pos: float, dur: float):
        if self.skin.volume_slider:
            self.skin.volume_slider.value = self.core.volume / 100.0

    def _on_core_state_change(self, state: str):
        self.skin_area.queue_draw()
        if hasattr(self, "mpris") and self.mpris:
            self.mpris.notify_playback_changed()

    def _on_core_file_end(self):
        # Auto-play next in playlist
        if self.current_index + 1 < len(self.playlist):
            self.play_index(self.current_index + 1)
        elif hasattr(self, "mpris") and self.mpris:
            self.mpris.notify_playback_changed()

    # --- Playlist & Playback Management ---

    def add_files_to_playlist(self, file_paths: List[str], auto_play: bool = False, clear_existing: bool = False) -> None:
        if clear_existing:
            self.playlist.clear()
            self.current_index = -1

        start_index = len(self.playlist)
        for fp in file_paths:
            self.playlist.append({
                "path": fp,
                "title": os.path.basename(fp),
                "duration": 0.0
            })
        self.playlist_window.update_playlist(self.playlist)

        if auto_play and len(self.playlist) > 0:
            target_index = start_index if start_index < len(self.playlist) else 0
            self.play_index(target_index)

    def play_index(self, index: int) -> None:
        if 0 <= index < len(self.playlist):
            self.current_index = index
            item = self.playlist[index]
            self.play_file(item["path"])

    def play_next(self) -> None:
        if len(self.playlist) > 0 and self.current_index + 1 < len(self.playlist):
            self.play_index(self.current_index + 1)
        elif len(self.playlist) > 0:
            self.play_index(0)

    def play_prev(self) -> None:
        if len(self.playlist) > 0 and self.current_index > 0:
            self.play_index(self.current_index - 1)
        elif len(self.playlist) > 0:
            self.play_index(len(self.playlist) - 1)

    def toggle_play_pause(self) -> None:
        self.core.play_pause()

    def remove_from_playlist(self, index: int) -> None:
        if 0 <= index < len(self.playlist):
            self.playlist.pop(index)
            if index == self.current_index:
                if len(self.playlist) > 0:
                    new_idx = min(index, len(self.playlist) - 1)
                    self.play_index(new_idx)
                else:
                    self.core.stop()
                    self.current_index = -1
            elif index < self.current_index:
                self.current_index -= 1
            self.playlist_window.update_playlist(self.playlist)

    def sort_playlist(self) -> None:
        cur_path = self.playlist[self.current_index]["path"] if 0 <= self.current_index < len(self.playlist) else None
        self.playlist.sort(key=lambda x: (x.get("title") or os.path.basename(x["path"])).lower())
        if cur_path:
            for i, it in enumerate(self.playlist):
                if it["path"] == cur_path:
                    self.current_index = i
                    break
        self.playlist_window.update_playlist(self.playlist)

    def shuffle_playlist(self) -> None:
        import random
        cur_path = self.playlist[self.current_index]["path"] if 0 <= self.current_index < len(self.playlist) else None
        random.shuffle(self.playlist)
        if cur_path:
            for i, it in enumerate(self.playlist):
                if it["path"] == cur_path:
                    self.current_index = i
                    break
        self.playlist_window.update_playlist(self.playlist)

    def set_subtitle_size(self, size_pt: int) -> None:
        self.sub_mgr.font_size = size_pt
        self.osd.show_osd(f"Subtitle Size: {size_pt} pt")

    def toggle_translation(self, active: bool) -> None:
        self.sub_mgr.translation_enabled = active
        self.osd.show_osd(f"AI Subtitle Translation: {'ON' if active else 'OFF'}")

    def play_file(self, file_path: str, seek_pts: float = 0.0) -> None:
        if self.core.wid is None:
            self._pending_playback = (file_path, seek_pts)
            self.set_title(f"Jonaki - {os.path.basename(file_path)}")
            return

        if seek_pts <= 0.0:
            saved_pts = self.db.get_playback_position(file_path)
            if saved_pts is not None and saved_pts > 5.0:
                seek_pts = saved_pts
                self.osd.show_osd(f"Resumed at {self.skin._format_time(saved_pts)}")

        self.core.load_file(file_path, start_pts=seek_pts)
        self.set_title(f"Jonaki - {os.path.basename(file_path)}")
        self.core.play()
        self.apply_audio_filters()
        if hasattr(self, "mpris") and self.mpris:
            self.mpris.notify_playback_changed()

    def set_repeat_a(self) -> None:
        pts = self.core.set_repeat_point_a()
        self.osd.show_osd(f"A-B Repeat: Point A Set ({self.skin._format_time(pts)})")

    def set_repeat_b(self) -> None:
        pts = self.core.set_repeat_point_b()
        if pts is not None:
            self.osd.show_osd(f"A-B Repeat: Point B Set ({self.skin._format_time(pts)})")

    def apply_audio_filters(self) -> None:
        for idx in range(10):
            gain = self.equalizer.get_band(idx)
            self.core.set_equalizer_band(idx, gain)
        self.core.set_audio_boost(self.dsp.audio_boost_db)
        self.core.set_normalizer(self.dsp.normalizer_enabled)

    def toggle_normalizer(self, active: bool) -> None:
        self.dsp.normalizer_enabled = active
        self.apply_audio_filters()

    def _open_file_dialog(self) -> None:
        dialog = Gtk.FileChooserDialog(title="Open Media File(s)", parent=self,
                                       action=Gtk.FileChooserAction.OPEN)
        dialog.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_OPEN, Gtk.ResponseType.OK)
        dialog.set_select_multiple(True)

        media_filter = Gtk.FileFilter()
        media_filter.set_name("All Media Files (*.mp4, *.mkv, *.webm, *.avi...)")
        for ext in ["*.mp4", "*.mkv", "*.webm", "*.avi", "*.mov", "*.flv", "*.wmv", "*.ts", "*.m2ts",
                    "*.mp3", "*.flac", "*.wav", "*.ogg", "*.m4a", "*.aac", "*.opus"]:
            media_filter.add_pattern(ext)
            media_filter.add_pattern(ext.upper())
        dialog.add_filter(media_filter)

        all_filter = Gtk.FileFilter()
        all_filter.set_name("All Files (*)")
        all_filter.add_pattern("*")
        dialog.add_filter(all_filter)

        if dialog.run() == Gtk.ResponseType.OK:
            files = dialog.get_filenames()
            if files:
                self.add_files_to_playlist(files, auto_play=True, clear_existing=True)
        dialog.destroy()

    def _open_folder_dialog(self) -> None:
        dialog = Gtk.FileChooserDialog(title="Open Media Folder", parent=self,
                                       action=Gtk.FileChooserAction.SELECT_FOLDER)
        dialog.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_OPEN, Gtk.ResponseType.OK)
        if dialog.run() == Gtk.ResponseType.OK:
            folder = dialog.get_filename()
            if folder and os.path.isdir(folder):
                media_exts = ('.mp4', '.mkv', '.webm', '.avi', '.mov', '.flv', '.wmv', '.ts', '.m2ts',
                              '.mp3', '.flac', '.wav', '.ogg', '.m4a', '.aac', '.opus')
                files = []
                for root, _, filenames in os.walk(folder):
                    for fn in sorted(filenames):
                        if fn.lower().endswith(media_exts):
                            files.append(os.path.join(root, fn))
                if files:
                    self.add_files_to_playlist(files, auto_play=True, clear_existing=True)
        dialog.destroy()

    def _open_url_dialog(self) -> None:
        dialog = Gtk.Dialog(title="Open URL", parent=self, flags=0)
        dialog.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_OK, Gtk.ResponseType.OK)
        box = dialog.get_content_area()
        entry = Gtk.Entry()
        entry.set_placeholder_text("https://... or rtsp://...")
        entry.set_width_chars(50)
        box.add(entry)
        dialog.show_all()
        if dialog.run() == Gtk.ResponseType.OK:
            url = entry.get_text().strip()
            if url:
                self.add_files_to_playlist([url], auto_play=True)
        dialog.destroy()

    def _open_from_clipboard(self) -> None:
        text = None
        try:
            clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
            text = clipboard.wait_for_text()
            if not text:
                primary = Gtk.Clipboard.get(Gdk.SELECTION_PRIMARY)
                text = primary.wait_for_text()
        except Exception as e:
            print(f"[Jonaki] Clipboard read error: {e}")

        # CLI fallback for Wayland / X11 if GTK clipboard returned empty
        if not text:
            import subprocess
            try:
                res = subprocess.run(["wl-paste", "--no-newline"], capture_output=True, text=True, timeout=1)
                if res.returncode == 0 and res.stdout.strip():
                    text = res.stdout.strip()
            except Exception:
                pass
        if not text:
            import subprocess
            try:
                res = subprocess.run(["xclip", "-selection", "clipboard", "-o"], capture_output=True, text=True, timeout=1)
                if res.returncode == 0 and res.stdout.strip():
                    text = res.stdout.strip()
            except Exception:
                pass

        if not text:
            self.osd.show_osd("Clipboard is empty")
            return

        text = text.strip().strip('"').strip("'")

        # 1. Check for URL (streaming, YouTube, RTSP, HTTP/HTTPS, HLS, DASH, etc.)
        url_schemes = ("http://", "https://", "rtsp://", "rtmp://", "mms://", "magnet:", "ytdl://", "udp://", "tcp://")
        if any(text.startswith(scheme) for scheme in url_schemes):
            self.add_files_to_playlist([text], auto_play=True, clear_existing=True)
            self.osd.show_osd(f"Playing from Clipboard: {text[:45]}...")
            return

        # 2. Check for local file path or file:// URI
        target_path = text
        if target_path.startswith("file://"):
            from urllib.parse import unquote
            target_path = unquote(target_path[7:])

        if os.path.exists(target_path):
            sub_exts = ('.srt', '.ass', '.ssa', '.vtt', '.smi', '.sub')
            if target_path.lower().endswith(sub_exts):
                self.core.load_subtitle(target_path)
                self.osd.show_osd(f"Subtitle Loaded: {os.path.basename(target_path)}")
            else:
                self.add_files_to_playlist([target_path], auto_play=True, clear_existing=True)
                self.osd.show_osd(f"Playing: {os.path.basename(target_path)}")
            return

        self.osd.show_osd("Clipboard does not contain a valid URL or media file")

    def _open_subtitle_dialog(self) -> None:
        dialog = Gtk.FileChooserDialog(title="Open Subtitle File", parent=self,
                                       action=Gtk.FileChooserAction.OPEN)
        dialog.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_OPEN, Gtk.ResponseType.OK)
        sub_filter = Gtk.FileFilter()
        sub_filter.set_name("Subtitle Files (*.srt, *.ass, *.ssa, *.vtt, *.smi)")
        for ext in ["*.srt", "*.ass", "*.ssa", "*.vtt", "*.smi", "*.sub"]:
            sub_filter.add_pattern(ext)
        dialog.add_filter(sub_filter)
        if dialog.run() == Gtk.ResponseType.OK:
            sub_file = dialog.get_filename()
            if sub_file:
                self.core.load_subtitle(sub_file)
                self.osd.show_osd(f"Subtitle Loaded: {os.path.basename(sub_file)}")
        dialog.destroy()

    def _show_about_dialog(self) -> None:
        about = Gtk.AboutDialog(parent=self)
        about.set_program_name("Jonaki")
        about.set_version("1.0.0 (Linux Native)")
        about.set_copyright("Jonaki Open Source Project")
        about.set_comments("Modern high-performance media player for Linux, inspired by PotPlayer.\nNative in-process libmpv hardware playback with zero external dependencies.")
        about.set_license_type(Gtk.License.GPL_3_0)
        about.set_website("https://github.com/jonaki-player/jonaki")
        about.run()
        about.destroy()

    def _on_destroy(self, widget):
        if hasattr(self, "mpris") and self.mpris:
            self.mpris.stop()
        if self.core.current_file and self.core.position > 5.0:
            try:
                self.db.save_playback_position(
                    self.core.current_file,
                    self.core.position,
                    duration=self.core.duration,
                    title=self.core.current_title or os.path.basename(self.core.current_file)
                )
            except Exception as e:
                print(f"[MediaDB] Failed to save resume position on exit: {e}")
        self.core.stop_engine()
        if Gtk.main_level() > 0:
            Gtk.main_quit()


# Backward compatibility alias
PotPlayerMainWindow = JonakiMainWindow
