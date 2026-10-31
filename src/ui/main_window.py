# SPDX-License-Identifier: GPL-3.0-or-later
"""
Jonaki for Linux - Main Player Window & Input Coordinator
Integrates MPV rendering surface, DSF skin overlay, keyboard shortcuts, and dialogs.
"""

import os
import sys
import time
import random
import threading
import json
from urllib.parse import unquote
import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
from gi.repository import Gtk, Gdk, GLib, GdkPixbuf
import cairo
from typing import Optional, List, Dict, Any

from core.engine import JonakiCore, PlaybackState
from core.media_db import MediaDatabase
from core.mpris import MPRIS2Service
from core.power_manager import PowerInhibitor
from ui.skin_engine import PotSkinEngine
from ui.osd_overlay import OSDOverlay
from ui.context_menu import PotContextMenu
from ui.control_box import ControlBoxDialog
from ui.playlist_view import PlaylistWindow
from ui.media_info_dialog import MediaInfoDialog
from ui.subtitle_search_dialog import SubtitleSearchDialog
from ui.subtitle_style_dialog import SubtitleStyleDialog
from audio.equalizer import EqualizerModel
from audio.dsp_chain import AudioDSPChain
from video.shader_manager import VideoShaderManager
from video.capture import MediaCaptureManager
from subtitle.subtitle_manager import SubtitleManager
from subtitle.translator import SubtitleTranslator
from torrent.manager import TorrentStreamManager
from ui.torrent_dialog import TorrentStreamDialog


def normalize_media_path(path: str) -> str:
    """Normalizes file:// URIs and filesystem paths to local paths."""
    if isinstance(path, str) and path.startswith("file://"):
        return unquote(path[7:])
    return path


class JonakiMainWindow(Gtk.Window):
    def __init__(self, initial_files: Optional[List[str]] = None, config_preset: str = "Default", db: Optional[MediaDatabase] = None):
        super().__init__(title="Jonaki")
        self.set_default_size(960, 580)
        self.set_position(Gtk.WindowPosition.CENTER)

        # Configure application and window icon (multi-resolution hierarchy)
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        icon_candidates = [
            os.path.join(base_dir, "assets", "logos", "jonaki.png"),
            os.path.expanduser("~/.local/share/icons/hicolor/256x256/apps/jonaki.png"),
            "/usr/share/icons/hicolor/256x256/apps/jonaki.png",
        ]
        sizes = [16, 24, 32, 48, 64, 128, 256]
        for icon_path in icon_candidates:
            if os.path.exists(icon_path):
                try:
                    pixbufs = [GdkPixbuf.Pixbuf.new_from_file_at_scale(icon_path, s, s, True) for s in sizes]
                    self.set_icon_list(pixbufs)
                    Gtk.Window.set_default_icon_list(pixbufs)
                    Gtk.Window.set_default_icon_name("jonaki")
                    break
                except Exception:
                    try:
                        self.set_icon_from_file(icon_path)
                        Gtk.Window.set_default_icon_from_file(icon_path)
                        break
                    except Exception:
                        pass

        # Set WM_CLASS and WM_WINDOW_ROLE explicitly for X11 / XWayland window managers
        if not GLib.get_prgname():
            GLib.set_prgname("jonaki")
        if not GLib.get_application_name():
            GLib.set_application_name("Jonaki")
        try:
            self.set_role("jonaki")
        except Exception:
            pass

        # Set RGBA visual for true alpha channel transparency over OpenGL
        screen = self.get_screen()
        rgba = screen.get_rgba_visual() if screen else None
        if rgba:
            self.set_visual(rgba)

        # Subsystems
        self.db = db if db is not None else MediaDatabase()
        self.equalizer = EqualizerModel()
        self.dsp = AudioDSPChain()
        # Audio Enhancement preferences (enabled by default on fresh installation)
        enh_enabled_saved = self.db.get_setting("audio_enhancement_enabled", "1")
        enh_preset_saved = self.db.get_setting("audio_enhancement_preset", "Balanced / Default")
        enh_gain_saved = self.db.get_setting("audio_enhancement_gain", "5.0")
        try:
            self.dsp.enhancement_gain_db = float(enh_gain_saved)
        except (ValueError, TypeError):
            self.dsp.enhancement_gain_db = 5.0
        self.dsp.set_enhancement_preset(enh_preset_saved)
        self.dsp.enhancement_enabled = (enh_enabled_saved == "1")

        # Master volume and mute preferences
        vol_saved = self.db.get_setting("master_volume", None)
        self._initial_volume = None
        if vol_saved is not None:
            try:
                self._initial_volume = max(0.0, min(100.0, float(vol_saved)))
            except (ValueError, TypeError):
                self._initial_volume = None
        mute_saved = self.db.get_setting("master_muted", "0")
        self._initial_muted = (mute_saved == "1")

        self.shader_mgr = VideoShaderManager()
        self.capture_mgr = MediaCaptureManager()
        self.sub_mgr = SubtitleManager()
        self.translator = SubtitleTranslator()
        self.skin = PotSkinEngine()
        self.osd = OSDOverlay()
        self.torrent_manager = TorrentStreamManager()
        self.power_inhibitor = PowerInhibitor()

        # Playback playlist queue
        self.playlist: List[Dict[str, Any]] = []
        self.current_index: int = -1
        self.is_fullscreen: bool = False
        self._last_mouse_move_time = time.time()
        self._last_mouse_pos = (-1, -1)
        self._last_seek_time: float = 0.0
        self._cursor_visible: bool = True
        self._controls_visible = True
        self._pending_playback: Optional[Any] = None
        self._is_keep_above: bool = False
        self._click_timer_id: Optional[int] = None
        self._translation_seq: int = 0
        self._last_sub_text: str = ""
        self._trans_in_progress: bool = False
        self._pending_trans: Optional[tuple] = None

        # Root vertical layout box
        self.main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add(self.main_box)

        # Core Playback Engine (libmpv C-FFI)
        self.core = JonakiCore()
        if self._initial_volume is not None:
            self.core.set_volume(self._initial_volume)
        if self._initial_muted:
            self.core.set_mute(True)
        self.core.on_time_update = lambda pos, dur: GLib.idle_add(self._on_core_time_update, pos, dur)
        self.core.on_state_change = lambda st: GLib.idle_add(self._on_core_state_change, st)
        self.core.on_file_end = lambda: GLib.idle_add(self._on_core_file_end)
        self.core.on_audio_filter_sync = lambda: GLib.idle_add(self.apply_audio_filters)

        # Route OSD messages to native GPU engine during active playback or paused file
        orig_show_osd = self.osd.show_osd
        def _show_osd_wrapper(text: str, duration_sec: float = 2.0):
            orig_show_osd(text, duration_sec)
            if self.core.state in (PlaybackState.PLAYING, PlaybackState.PAUSED) and self.core.current_file:
                clean = text.replace('"', '\\"')
                self.core.command(f'show-text "{clean}" {int(duration_sec * 1000)}')
        self.osd.show_osd = _show_osd_wrapper

        # Video Surface with Overlay (Gtk.Overlay)
        self.video_overlay = Gtk.Overlay()

        self.video_area = Gtk.DrawingArea()
        self.video_area.set_can_focus(True)
        self.video_area.connect("realize", self._on_video_realize)

        video_events = (Gdk.EventMask.BUTTON_PRESS_MASK |
                        Gdk.EventMask.BUTTON_RELEASE_MASK |
                        Gdk.EventMask.POINTER_MOTION_MASK |
                        Gdk.EventMask.SCROLL_MASK |
                        Gdk.EventMask.ENTER_NOTIFY_MASK |
                        Gdk.EventMask.LEAVE_NOTIFY_MASK |
                        Gdk.EventMask.KEY_PRESS_MASK)
        self.video_area.add_events(video_events)
        self.video_area.connect("button-press-event", self._on_video_button_press)
        self.video_area.connect("scroll-event", self._on_video_scroll)
        self.video_area.connect("motion-notify-event", self._on_mouse_motion)
        self.video_area.connect("enter-notify-event", self._on_mouse_motion)
        self.video_overlay.add(self.video_area)

        # Cairo overlay layer for logo and OSD text / Tab Tech HUD
        self.osd_layer = Gtk.DrawingArea()
        if rgba:
            self.osd_layer.set_visual(rgba)
        self.osd_layer.set_app_paintable(True)
        self.osd_layer.connect("draw", self._on_draw_video_area)
        self.osd_layer.connect("realize", self._on_osd_realize)
        self.osd_layer.add_events(video_events)
        self.osd_layer.connect("button-press-event", self._on_video_button_press)
        self.osd_layer.connect("scroll-event", self._on_video_scroll)
        self.osd_layer.connect("motion-notify-event", self._on_mouse_motion)
        self.osd_layer.connect("enter-notify-event", self._on_mouse_motion)
        self.video_overlay.add_overlay(self.osd_layer)
        self.video_overlay.set_overlay_pass_through(self.osd_layer, True)

        # Fullscreen Top Bar Overlay (32px: media title + window minimize/restore/close)
        self.top_bar = Gtk.DrawingArea()
        self.top_bar.set_size_request(-1, 32)
        self.top_bar.set_valign(Gtk.Align.START)
        self.top_bar.set_halign(Gtk.Align.FILL)
        self.top_bar.set_no_show_all(True)
        if rgba:
            self.top_bar.set_visual(rgba)
        self.top_bar.set_app_paintable(True)
        self.top_bar.connect("draw", self._on_draw_top_bar)
        self.top_bar.add_events(Gdk.EventMask.BUTTON_PRESS_MASK |
                                Gdk.EventMask.BUTTON_RELEASE_MASK |
                                Gdk.EventMask.POINTER_MOTION_MASK |
                                Gdk.EventMask.ENTER_NOTIFY_MASK |
                                Gdk.EventMask.LEAVE_NOTIFY_MASK)
        self.top_bar.connect("button-press-event", self._on_top_bar_button_press)
        self.top_bar.connect("motion-notify-event", self._on_top_bar_motion)
        self.top_bar.connect("leave-notify-event", self._on_top_bar_leave)
        self.top_bar.connect("enter-notify-event", self._on_mouse_motion)
        self.video_overlay.add_overlay(self.top_bar)

        self.main_box.pack_start(self.video_overlay, True, True, 0)

        # Bottom Skin Control Bar Area (62px: 22px upper slider strip + 40px lower button strip)
        # Positioned inside video_overlay at bottom (valign=END) so hiding/showing it never resizes video
        self.skin_area = Gtk.DrawingArea()
        self.skin_area.set_size_request(-1, 62)
        self.skin_area.set_valign(Gtk.Align.END)
        self.skin_area.set_halign(Gtk.Align.FILL)
        self.skin_area.connect("draw", self._on_draw_skin_area)
        self.skin_area.add_events(Gdk.EventMask.BUTTON_PRESS_MASK |
                                 Gdk.EventMask.BUTTON_RELEASE_MASK |
                                 Gdk.EventMask.POINTER_MOTION_MASK |
                                 Gdk.EventMask.ENTER_NOTIFY_MASK |
                                 Gdk.EventMask.SCROLL_MASK)
        self.skin_area.connect("button-press-event", self._on_skin_button_press)
        self.skin_area.connect("button-release-event", self._on_skin_button_release)
        self.skin_area.connect("motion-notify-event", self._on_skin_motion)
        self.skin_area.connect("enter-notify-event", self._on_mouse_motion)
        self.skin_area.connect("scroll-event", self._on_skin_scroll)
        self.video_overlay.add_overlay(self.skin_area)

        # Right-click context menu
        self.context_menu = PotContextMenu(self.handle_command)

        # Secondary Windows
        self.control_box = ControlBoxDialog(self)
        self.playlist_window = PlaylistWindow(self)
        self.media_info_dialog = MediaInfoDialog(self)

        # Window events (also listen on toplevel so any mouse activity unhides cursor and handles right click)
        self.add_events(Gdk.EventMask.POINTER_MOTION_MASK |
                        Gdk.EventMask.ENTER_NOTIFY_MASK |
                        Gdk.EventMask.BUTTON_PRESS_MASK |
                        Gdk.EventMask.BUTTON_RELEASE_MASK)
        self.connect("motion-notify-event", self._on_mouse_motion)
        self.connect("enter-notify-event", self._on_mouse_motion)
        self.connect("button-press-event", self._on_window_button_press)
        self.connect("button-release-event", self._on_window_button_release)
        self.connect("window-state-event", self._on_window_state_event)
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
        self._ui_timer_id = GLib.timeout_add(100, self._on_ui_tick)

        if initial_files:
            clean_files = [normalize_media_path(f) for f in initial_files]
            self.add_files_to_playlist(clean_files, auto_play=True)
        else:
            # Restore saved playlist from MediaDatabase if available
            try:
                saved_items = self.db.get_playlist_items()
                if saved_items:
                    for row in saved_items:
                        fp = normalize_media_path(row.get("file_path", ""))
                        if fp and (os.path.exists(fp) or any(fp.startswith(p) for p in ("http://", "https://", "rtsp://", "rtmp://", "ytdl://"))):
                            self.playlist.append({
                                "path": fp,
                                "title": row.get("title") or os.path.basename(fp),
                                "duration": row.get("duration", 0.0)
                            })
                    if self.playlist:
                        self.playlist_window.update_playlist(self.playlist)
            except Exception as e:
                print(f"[MediaDB] Failed to restore playlist: {e}")

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
        self.apply_subtitle_style()

        if getattr(self, "_pending_playback", None):
            pending = self._pending_playback
            self._pending_playback = None
            if len(pending) == 4:
                fp, pts, sub_f, aud_f = pending
                self.play_file(fp, seek_pts=pts, sub_file=sub_f, audio_file=aud_f)
            else:
                fp, pts = pending[:2]
                self.play_file(fp, seek_pts=pts)
        elif len(self.playlist) > 0 and self.current_index >= 0:
            self.play_index(self.current_index)

    def _on_osd_realize(self, widget):
        gdk_win = widget.get_window()
        if gdk_win and hasattr(gdk_win, "set_pass_through"):
            try:
                gdk_win.set_pass_through(True)
            except Exception:
                pass


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
                    if path.lower().endswith(".torrent"):
                        self._open_torrent_dialog(initial_source=path)
                        context.finish(True, False, time_val)
                        return
                    files.append(path)
            elif uri.startswith("magnet:"):
                self._open_torrent_dialog(initial_source=uri)
                context.finish(True, False, time_val)
                return
            elif uri.startswith("http://") or uri.startswith("https://"):
                files.append(uri)

        if files:
            sub_exts = ('.srt', '.ass', '.ssa', '.vtt', '.smi', '.sub')
            subs = [f for f in files if f.lower().endswith(sub_exts)]
            media = [f for f in files if not f.lower().endswith(sub_exts)]
            if media:
                first_sub = subs[0] if subs else None
                self.add_files_to_playlist(media, auto_play=True, clear_existing=True, sub_file=first_sub)
                if len(subs) > 1:
                    for s in subs[1:]:
                        self.core.load_subtitle(s)
            elif subs:
                for s in subs:
                    self.core.load_subtitle(s)
                    self.osd.show_osd(f"Subtitle: {os.path.basename(s)}")
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
                self._translation_seq += 1
                seq = self._translation_seq
                dst = self.sub_mgr.target_language
                if self._trans_in_progress:
                    self._pending_trans = (sub_text, dst, seq)
                else:
                    self._start_translation_worker(sub_text, dst, seq)
            elif not sub_text and getattr(self, "_last_sub_text", ""):
                self._last_sub_text = ""

        # Dynamic overlay layer visibility: Only display osd_layer when idle (for logo)
        # or when Tab Tech HUD or translated subtitle is requested during playback.
        # Transient OSD messages during active playback are handled by mpv's native GPU OSD
        # to prevent X11/XWayland subwindow clipping, buffer clearing, and frame flickering.
        is_active_playback = bool(self.core.state in (PlaybackState.PLAYING, PlaybackState.PAUSED) and self.core.current_file)
        if is_active_playback:
            show_overlay = has_hud or has_sub
        else:
            show_overlay = has_hud or has_sub or is_idle or has_osd
        if show_overlay:
            if not self.osd_layer.get_visible():
                self.osd_layer.show()
            self.osd_layer.queue_draw()
        else:
            if self.osd_layer.get_visible():
                self.osd_layer.hide()

        # Auto-hide controls in fullscreen & cursor during active playback
        if self.core.state == PlaybackState.PLAYING:
            # Keep PC awake and prevent display dimming via periodic power inhibitor heartbeat
            if hasattr(self, "power_inhibitor") and self.power_inhibitor:
                self.power_inhibitor.heartbeat()

            if time.time() - self._last_mouse_move_time > 2.5:
                # In fullscreen, auto-hide the bottom skin control bar and top bar
                if self.is_fullscreen and self._controls_visible:
                    self.skin_area.hide()
                    if hasattr(self, "top_bar") and self.top_bar:
                        self.top_bar.hide()
                    self._controls_visible = False
                # Auto-hide cursor over video after 2.5 seconds of inactivity
                if self._cursor_visible:
                    self._set_cursor_visible(False)
        else:
            # When paused, stopped, or idle: cursor & controls should always be visible
            if not self._cursor_visible:
                self._set_cursor_visible(True)
            if not self._controls_visible:
                self.skin_area.show()
                if self.is_fullscreen and hasattr(self, "top_bar") and self.top_bar:
                    self.top_bar.show()
                self._controls_visible = True
        return True

    def _start_translation_worker(self, txt: str, dst: str, seq: int) -> None:
        self._trans_in_progress = True
        def _trans_worker():
            tr = self.translator.translate(txt, dst_lang=dst)
            def _finish():
                self._trans_in_progress = False
                if seq == self._translation_seq:
                    self.osd.set_translated_sub(tr, 4.0)
                if self._pending_trans is not None:
                    next_txt, next_dst, next_seq = self._pending_trans
                    self._pending_trans = None
                    self._start_translation_worker(next_txt, next_dst, next_seq)
                return False
            GLib.idle_add(_finish)
        threading.Thread(target=_trans_worker, daemon=True).start()

    # --- Draw Handlers ---

    def _on_draw_video_area(self, widget, cr: cairo.Context):
        alloc = widget.get_allocation()
        w, h = alloc.width, alloc.height

        # Always clear overlay background to 100% transparent alpha first
        cr.save()
        cr.set_operator(cairo.OPERATOR_CLEAR)
        cr.paint()
        cr.restore()

        # If no video is playing and no file loaded, draw logo background
        if self.core.state in (PlaybackState.IDLE, PlaybackState.STOPPED) and not self.core.current_file:
            logo_surf = (
                self.skin.surfaces.get("jonaki.png")
                or self.skin.surfaces.get("Jonaki.png")
                or self.skin.surfaces.get("dsf_logo.png")
            )

            is_dsf = bool(
                logo_surf
                and (
                    logo_surf is self.skin.surfaces.get("dsf_logo.png")
                )
            )

            # Match background canvas to logo palette
            if is_dsf:
                # DSF bitmap background is ~#101010
                cr.set_source_rgb(0.063, 0.063, 0.063)
            elif logo_surf:
                # Jonaki logo background is deep dark #020203
                cr.set_source_rgb(0.01, 0.01, 0.015)
            else:
                cr.set_source_rgb(0.05, 0.05, 0.06)

            cr.rectangle(0, 0, w, h)
            cr.fill()

            if logo_surf:
                surf_w = logo_surf.get_width()
                surf_h = logo_surf.get_height()
                if surf_w > 0 and surf_h > 0:
                    if is_dsf:
                        # DSF logo is 596x443 with embedded typography
                        max_w = min(596.0, max(120.0, w * 0.85))
                        max_h = min(443.0, max(100.0, h * 0.85))
                        scale = min(max_w / surf_w, max_h / surf_h)
                        draw_w = surf_w * scale
                        draw_h = surf_h * scale
                        draw_x = (w - draw_w) / 2.0
                        draw_y = (h - draw_h) / 2.0

                        cr.save()
                        cr.translate(draw_x, draw_y)
                        cr.scale(scale, scale)
                        cr.set_source_surface(logo_surf, 0, 0)
                        cr.paint()
                        cr.restore()
                    else:
                        # Jonaki emblem logo (square/circular emblem)
                        max_w = min(220.0, max(32.0, w * 0.4))
                        max_h = min(220.0, max(32.0, h * 0.35))
                        scale = min(max_w / surf_w, max_h / surf_h)
                        draw_w = surf_w * scale
                        draw_h = surf_h * scale
                        draw_x = (w - draw_w) / 2.0
                        draw_y = max(10.0, (h - draw_h) / 2.0 - (20.0 if h >= 220 else 0.0))

                        cr.save()
                        cr.translate(draw_x, draw_y)
                        cr.scale(scale, scale)
                        cr.set_source_surface(logo_surf, 0, 0)
                        cr.paint()
                        cr.restore()

                        # Jonaki typography below emblem if vertical space permits
                        if h >= 200:
                            cr.save()
                            cr.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
                            cr.set_font_size(20.0)
                            cr.set_source_rgb(0.85, 0.85, 0.9)
                            title_text = "Jonaki"
                            ext = cr.text_extents(title_text)
                            title_y = draw_y + draw_h + 28.0
                            cr.move_to((w - ext.width) / 2.0, title_y)
                            cr.show_text(title_text)

                            cr.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
                            cr.set_font_size(12.0)
                            cr.set_source_rgb(0.48, 0.5, 0.55)
                            sub_text = "Multimedia Player"
                            ext_sub = cr.text_extents(sub_text)
                            cr.move_to((w - ext_sub.width) / 2.0, title_y + 18.0)
                            cr.show_text(sub_text)
                            cr.restore()
            else:
                # Vector fallback when no bitmap logo is found
                cr.save()
                cr.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
                cr.set_font_size(26.0)
                cr.set_source_rgb(0.55, 0.55, 0.6)
                text = "Jonaki"
                ext = cr.text_extents(text)
                cr.move_to((w - ext.width) / 2.0, (h / 2.0) - 2.0)
                cr.show_text(text)

                cr.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
                cr.set_font_size(13.0)
                cr.set_source_rgb(0.38, 0.4, 0.44)
                sub_text = "Multimedia Player"
                ext_sub = cr.text_extents(sub_text)
                cr.move_to((w - ext_sub.width) / 2.0, (h / 2.0) + 24.0)
                cr.show_text(sub_text)
                cr.restore()

        # Draw OSD notifications and Tab Technical Info HUD
        pix_fmt = self.core.get_property("video-format") or self.core.get_property("pixelformat") or "YUV420P"
        sr = self.core.get_property("audio-params/samplerate") or 48000
        drop_frames = self.core.get_property("drop-frame-count") or 0
        info = {
            "file_path": self.core.current_file or "None",
            "video_codec": self.core.video_codec or "Auto",
            "audio_codec": self.core.audio_codec or "Auto",
            "hwdec": self.core.hwdec_active,
            "width": self.core.video_width if self.core.video_width > 0 else 1920,
            "height": self.core.video_height if self.core.video_height > 0 else 1080,
            "aspect": self.core.video_aspect or "16:9",
            "fps": self.core.video_fps if self.core.video_fps > 0 else 60.0,
            "pixel_format": str(pix_fmt).upper(),
            "sample_rate": sr,
            "dropped_frames": drop_frames,
            "audio_channels": self.core.audio_channels or 2
        }
        is_active = bool(self.core.state in (PlaybackState.PLAYING, PlaybackState.PAUSED) and self.core.current_file)
        self.osd.render(cr, w, h, info, self.core.position, self.core.duration, skip_transient_osd=is_active)

    def _on_draw_skin_area(self, widget, cr: cairo.Context):
        alloc = widget.get_allocation()
        w, h = alloc.width, alloc.height
        is_playing = (self.core.state == PlaybackState.PLAYING)
        bms = [b["timestamp"] for b in self.db.get_bookmarks(self.core.current_file or "")]
        chapters = [float(c.get("time", 0.0)) for c in self.core.get_chapters()]

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
                         bookmarks=bms, media_info=media_info, chapters=chapters)

    def _on_draw_top_bar(self, widget, cr: cairo.Context):
        if not self.is_fullscreen:
            return
        alloc = widget.get_allocation()
        w, h = alloc.width, alloc.height
        title = self.core.current_title or "Jonaki"
        file_ext = ""
        if self.core.current_file:
            _, ext = os.path.splitext(self.core.current_file)
            file_ext = ext
        self.skin.render_top_bar(cr, w, h, title=title, is_fullscreen=True,
                                 file_type=file_ext, is_keep_above=getattr(self, "_is_keep_above", False))

    def _on_top_bar_button_press(self, widget, event):
        self._on_mouse_motion(widget, event)
        if event.button == 1:
            hit = self.skin.hit_test_top_bar(int(event.x), int(event.y))
            if hit and hasattr(hit, "cmd_id"):
                hit.state = 2  # Pressed
                self.top_bar.queue_draw()
                if hit.cmd_id == "CMD_MAIN_MENU":
                    self.context_menu.popup(event, self.core, recent_files=self.db.get_recent_history(15))
                elif hit.cmd_id == "ID_ETC_NEXTONTOP":
                    self._is_keep_above = not getattr(self, "_is_keep_above", False)
                    self.set_keep_above(self._is_keep_above)
                    self.osd.show_osd(f"Stay on Top: {'ON' if self._is_keep_above else 'OFF'}")
                    self.top_bar.queue_draw()
                else:
                    self.handle_command(hit.cmd_id)
                return True
        elif event.button == 3:
            self.context_menu.popup(event, self.core, recent_files=self.db.get_recent_history(15))
            return True
        return False

    def _on_top_bar_motion(self, widget, event):
        self._on_mouse_motion(widget, event)
        x, y = int(event.x), int(event.y)
        hovered_btn = None
        for btn in getattr(self.skin, "top_buttons", []):
            bx, by, bw, bh = btn.rect
            if bx - 2 <= x <= bx + bw + 2 and by - 2 <= y <= by + bh + 2:
                btn.state = 1  # Hover
                hovered_btn = btn
            else:
                btn.state = 0
        if hovered_btn:
            widget.set_tooltip_text(hovered_btn.tooltip)
        else:
            widget.set_tooltip_text(None)
        self.top_bar.queue_draw()
        return False

    def _on_top_bar_leave(self, widget, event):
        for btn in getattr(self.skin, "top_buttons", []):
            btn.state = 0
        self.top_bar.queue_draw()
        return False

    # --- Mouse & Interaction Handlers ---

    def _set_cursor_visible(self, visible: bool):
        self._cursor_visible = visible
        cursor = None if visible else Gdk.Cursor.new_for_display(Gdk.Display.get_default(), Gdk.CursorType.BLANK_CURSOR)

        # Apply to toplevel window
        top_win = self.get_window()
        if top_win:
            top_win.set_cursor(cursor)

        # Apply directly to video area window so child X11/Wayland surface reflects state immediately
        if hasattr(self, "video_area") and self.video_area:
            vid_win = self.video_area.get_window()
            if vid_win:
                vid_win.set_cursor(cursor)

        # Apply to OSD overlay layer
        if hasattr(self, "osd_layer") and self.osd_layer:
            osd_win = self.osd_layer.get_window()
            if osd_win:
                osd_win.set_cursor(cursor)

    def _on_mouse_motion(self, widget, event):
        cur_pos = (int(getattr(event, "x_root", getattr(event, "x", 0))),
                   int(getattr(event, "y_root", getattr(event, "y", 0))))
        if cur_pos == self._last_mouse_pos and self._cursor_visible and self._controls_visible:
            return False

        self._last_mouse_pos = cur_pos
        self._last_mouse_move_time = time.time()

        # Unhide cursor immediately upon any mouse movement
        if not self._cursor_visible:
            self._set_cursor_visible(True)

        # Unhide controls if they were auto-hidden in fullscreen
        if not self._controls_visible:
            self.skin_area.show()
            if self.is_fullscreen and hasattr(self, "top_bar") and self.top_bar:
                self.top_bar.show()
            self._controls_visible = True
        elif self.is_fullscreen and hasattr(self, "top_bar") and self.top_bar and not self.top_bar.get_visible():
            self.top_bar.show()

        return False

    def _on_video_button_press(self, widget, event):
        self._on_mouse_motion(widget, event)
        self.video_area.grab_focus()
        if event.button == 1:
            if event.type == Gdk.EventType._2BUTTON_PRESS:
                if self._click_timer_id:
                    GLib.source_remove(self._click_timer_id)
                    self._click_timer_id = None
                self.toggle_fullscreen()
            elif event.type == Gdk.EventType.BUTTON_PRESS:
                if self._click_timer_id:
                    GLib.source_remove(self._click_timer_id)
                    self._click_timer_id = None
                def _do_click():
                    self._click_timer_id = None
                    self.toggle_play_pause()
                    return False
                self._click_timer_id = GLib.timeout_add(250, _do_click)
        elif event.button == 2:
            # Middle-click: Play / Pause toggle
            if self._click_timer_id:
                GLib.source_remove(self._click_timer_id)
                self._click_timer_id = None
            self.toggle_play_pause()
            return True
        elif event.button == 3:
            if self._click_timer_id:
                GLib.source_remove(self._click_timer_id)
                self._click_timer_id = None
            self.context_menu.popup(event, self.core, recent_files=self.db.get_recent_history(15))
        elif event.button == 8:
            # Mouse back button: previous file
            self.play_prev()
            return True
        elif event.button == 9:
            # Mouse forward button: next file
            self.play_next()
            return True
        return True

    def _on_window_button_press(self, widget, event):
        if event.button == 3:
            if self._click_timer_id:
                GLib.source_remove(self._click_timer_id)
                self._click_timer_id = None
            self.context_menu.popup(event, self.core, recent_files=self.db.get_recent_history(15))
            return True
        return False

    def _on_window_button_release(self, widget, event):
        # Global window button-release handler: resets skin seek and volume dragging safely
        if getattr(self.skin.timebar, "is_dragging", False) or getattr(self.skin.volume_slider, "is_dragging", False):
            self._on_skin_button_release(widget, event)
        return False

    def _on_video_scroll(self, widget, event):
        if event.direction == Gdk.ScrollDirection.UP:
            self.core.adjust_volume(+2.0)
            self._save_audio_settings()
            self.osd.show_osd(f"Volume: {int(self.core.volume)}%")
        elif event.direction == Gdk.ScrollDirection.DOWN:
            self.core.adjust_volume(-2.0)
            self._save_audio_settings()
            self.osd.show_osd(f"Volume: {int(self.core.volume)}%")
        elif event.direction == Gdk.ScrollDirection.SMOOTH:
            _, delta_y = event.get_scroll_deltas()
            if abs(delta_y) > 0.01:
                step = max(0.5, min(5.0, abs(delta_y) * 2.0))
                change = +step if delta_y < 0 else -step
                self.core.adjust_volume(change)
                self._save_audio_settings()
                self.osd.show_osd(f"Volume: {int(self.core.volume)}%")
        return True

    def _on_skin_scroll(self, widget, event):
        x = int(getattr(event, "x", 0))
        y = int(getattr(event, "y", 0))
        # If scroll is over the timebar, perform relative seeking (+5s / -5s)
        if self.skin.timebar:
            tx, ty, tw, th = self.skin.timebar.rect
            if tx <= x <= tx + tw and ty - 3 <= y <= ty + th + 4:
                direction = event.direction
                if direction == Gdk.ScrollDirection.UP:
                    self.core.seek_relative(+5.0)
                    self.osd.show_osd("Seek: +5 sec")
                    return True
                elif direction == Gdk.ScrollDirection.DOWN:
                    self.core.seek_relative(-5.0)
                    self.osd.show_osd("Seek: -5 sec")
                    return True
                elif direction == Gdk.ScrollDirection.SMOOTH:
                    _, dy = event.get_scroll_deltas()
                    if abs(dy) > 0.01:
                        delta = -5.0 if dy > 0 else 5.0
                        self.core.seek_relative(delta)
                        self.osd.show_osd(f"Seek: {'+5' if delta > 0 else '-5'} sec")
                        return True

        # Otherwise route through volume scroll
        return self._on_video_scroll(widget, event)

    def _on_skin_button_press(self, widget, event):
        self._on_mouse_motion(widget, event)
        if event.button == 3:
            if self._click_timer_id:
                GLib.source_remove(self._click_timer_id)
                self._click_timer_id = None
            self.context_menu.popup(event, self.core, recent_files=self.db.get_recent_history(15))
            return True
        is_playing = (self.core.state == PlaybackState.PLAYING)
        hit = self.skin.hit_test(int(event.x), int(event.y), is_playing=is_playing)
        if hit:
            if hit == self.skin.timebar:
                self.skin.timebar.is_dragging = True
                self.skin.timebar.state = 2  # Down
                tx, ty, tw, th = self.skin.timebar.rect
                ratio = max(0.0, min(1.0, (event.x - tx) / tw))
                self.skin.timebar.drag_ratio = ratio
                self._last_seek_time = time.time()
                self.core.seek_percent(ratio * 100.0)
            elif hit == self.skin.volume_slider:
                self.skin.volume_slider.is_dragging = True
                self.skin.volume_slider.state = 2  # Down
                vx, vy, vw, vh = self.skin.volume_slider.rect
                ratio = max(0.0, min(1.0, (event.x - vx) / vw))
                self.skin.volume_slider.value = ratio
                self.core.set_volume(ratio * 100.0)
            elif hasattr(hit, "cmd_id"):
                hit.state = 2  # Pressed
                self.handle_command(hit.cmd_id)
        self.skin_area.queue_draw()

    def _on_skin_button_release(self, widget, event):
        if self.skin.timebar:
            if self.skin.timebar.is_dragging and self.skin.timebar.drag_ratio is not None:
                self.core.seek_percent(self.skin.timebar.drag_ratio * 100.0)
            self.skin.timebar.is_dragging = False
            self.skin.timebar.drag_ratio = None
            self.skin.timebar.state = 0
        if self.skin.volume_slider:
            if self.skin.volume_slider.is_dragging:
                self._save_audio_settings()
            self.skin.volume_slider.is_dragging = False
            self.skin.volume_slider.state = 0
        for btn in self.skin.buttons + self.skin.badges:
            btn.state = 0
        self.skin_area.queue_draw()

    def _on_skin_motion(self, widget, event):
        self._on_mouse_motion(widget, event)
        x, y = int(event.x), int(event.y)
        if self.skin.timebar and self.skin.timebar.is_dragging:
            tx, ty, tw, th = self.skin.timebar.rect
            ratio = max(0.0, min(1.0, (x - tx) / tw))
            self.skin.timebar.drag_ratio = ratio
            now = time.time()
            if now - getattr(self, "_last_seek_time", 0.0) >= 0.06:
                self._last_seek_time = now
                self.core.seek_percent(ratio * 100.0)
        elif self.skin.volume_slider and self.skin.volume_slider.is_dragging:
            vx, vy, vw, vh = self.skin.volume_slider.rect
            ratio = max(0.0, min(1.0, (x - vx) / vw))
            self.skin.volume_slider.value = ratio
            self.core.set_volume(ratio * 100.0)
        else:
            hovered_tooltip = None
            if self.skin.timebar:
                tx, ty, tw, th = self.skin.timebar.rect
                is_tb_hover = (tx <= x <= tx + tw and ty - 3 <= y <= ty + th + 4)
                self.skin.timebar.state = 1 if is_tb_hover else 0
                if is_tb_hover and getattr(self.core, "duration", 0) > 0:
                    hover_ratio = max(0.0, min(1.0, (x - tx) / tw))
                    hover_sec = hover_ratio * self.core.duration
                    hovered_tooltip = f"Seek: {self.skin._format_time(hover_sec, self.core.duration)}"
            if self.skin.volume_slider:
                vx, vy, vw, vh = self.skin.volume_slider.rect
                is_vol_hover = (vx <= x <= vx + vw and vy - 3 <= y <= vy + vh + 4)
                self.skin.volume_slider.state = 1 if is_vol_hover else 0
                if is_vol_hover:
                    hovered_tooltip = f"Volume: {int(self.core.volume)}%"
            is_playing = (self.core.state == PlaybackState.PLAYING)
            for btn in self.skin.buttons + self.skin.badges:
                if btn == self.skin.btn_play and is_playing:
                    btn.state = 0
                    continue
                if btn == self.skin.btn_pause and not is_playing:
                    btn.state = 0
                    continue
                bx, by, bw, bh = btn.rect
                if bx <= x <= bx + bw and by <= y <= by + bh:
                    btn.state = 1  # Hover
                    if getattr(btn, "tooltip", None):
                        hovered_tooltip = btn.tooltip
                else:
                    btn.state = 0
            widget.set_tooltip_text(hovered_tooltip)
        self.skin_area.queue_draw()

    # --- Keyboard Shortcut Dispatcher ---

    def _on_key_press(self, widget, event):
        focus = self.get_focus()
        if isinstance(focus, (Gtk.Entry, Gtk.TextView, Gtk.SearchEntry)):
            return False

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
        if ctrl and keyval in (Gdk.KEY_m, Gdk.KEY_M):
            self._open_torrent_dialog()
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

        # Video Frame Scaling & Zoom Shortcuts (Alternative: Shift + Alt + Arrows)
        if shift and alt and not ctrl:
            if keyval in (Gdk.KEY_Up, Gdk.KEY_KP_Up):
                self.handle_command("CMD_VIDEO_SCALE_HEIGHT_UP")
                return True
            if keyval in (Gdk.KEY_Down, Gdk.KEY_KP_Down):
                self.handle_command("CMD_VIDEO_SCALE_HEIGHT_DOWN")
                return True
            if keyval in (Gdk.KEY_Right, Gdk.KEY_KP_Right):
                self.handle_command("CMD_VIDEO_SCALE_WIDTH_UP")
                return True
            if keyval in (Gdk.KEY_Left, Gdk.KEY_KP_Left):
                self.handle_command("CMD_VIDEO_SCALE_WIDTH_DOWN")
                return True

        # Video Frame Zoom In:
        # - Alternative: Shift + Alt + =/+, Alt + =/+, Ctrl + Alt + =/+
        # - Numpad: KP_9 (NumLock ON), KP_Add, KP_Equal
        is_zoom_in_key = keyval in (Gdk.KEY_equal, Gdk.KEY_plus, Gdk.KEY_KP_Equal, Gdk.KEY_KP_Add)
        if is_zoom_in_key:
            if (shift and alt and not ctrl) or (alt and not ctrl and not shift) or (ctrl and alt):
                self.handle_command("CMD_VIDEO_ZOOM_IN")
                return True
            if keyval in (Gdk.KEY_KP_Add, Gdk.KEY_KP_Equal) and not ctrl:
                self.handle_command("CMD_VIDEO_ZOOM_IN")
                return True

        # Video Frame Zoom Out:
        # - Alternative: Shift + Alt + -/_, Alt + -/_, Ctrl + Alt + -/_
        # - Numpad: KP_1 (NumLock ON), KP_Subtract
        is_zoom_out_key = keyval in (Gdk.KEY_minus, Gdk.KEY_underscore, Gdk.KEY_KP_Subtract)
        if is_zoom_out_key:
            if (shift and alt and not ctrl) or (alt and not ctrl and not shift) or (ctrl and alt):
                self.handle_command("CMD_VIDEO_ZOOM_OUT")
                return True
            if keyval == Gdk.KEY_KP_Subtract and not ctrl:
                self.handle_command("CMD_VIDEO_ZOOM_OUT")
                return True

        # Video Frame Reset Dimensions:
        # - Alternative: Shift + Alt + 0/), Alt + 0, Ctrl + Alt + 0
        # - Numpad: KP_5, KP_Begin
        is_reset_key = keyval in (Gdk.KEY_0, Gdk.KEY_KP_0, Gdk.KEY_KP_Insert, Gdk.KEY_parenright)
        if is_reset_key:
            if (shift and alt and not ctrl) or (alt and not ctrl and not shift) or (ctrl and alt):
                self.handle_command("CMD_VIDEO_SCALE_RESET")
                return True

        # Video Frame Scaling & Zoom Shortcuts (Numpad with NumLock: KP_8, KP_2, KP_6, KP_4, KP_5, KP_9, KP_1)
        if not (ctrl or alt or shift):
            if keyval == Gdk.KEY_KP_8:
                self.handle_command("CMD_VIDEO_SCALE_HEIGHT_UP")
                return True
            if keyval == Gdk.KEY_KP_2:
                self.handle_command("CMD_VIDEO_SCALE_HEIGHT_DOWN")
                return True
            if keyval == Gdk.KEY_KP_6:
                self.handle_command("CMD_VIDEO_SCALE_WIDTH_UP")
                return True
            if keyval == Gdk.KEY_KP_4:
                self.handle_command("CMD_VIDEO_SCALE_WIDTH_DOWN")
                return True
            if keyval in (Gdk.KEY_KP_5, Gdk.KEY_KP_Begin):
                self.handle_command("CMD_VIDEO_SCALE_RESET")
                return True
            if keyval == Gdk.KEY_KP_9:
                self.handle_command("CMD_VIDEO_ZOOM_IN")
                return True
            if keyval == Gdk.KEY_KP_1:
                self.handle_command("CMD_VIDEO_ZOOM_OUT")
                return True

        # Left / Right Seeks & Alt+Left/Right Subtitle Sync
        if keyval in (Gdk.KEY_Left, Gdk.KEY_KP_Left):
            if alt and not (ctrl or shift):
                offset = self.sub_mgr.adjust_sync(-0.5)
                self.core.set_subtitle_delay(offset)
                self.osd.show_osd(f"Subtitle Sync: {offset:+.1f}s")
            elif ctrl and alt:
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
            if alt and not (ctrl or shift):
                offset = self.sub_mgr.adjust_sync(+0.5)
                self.core.set_subtitle_delay(offset)
                self.osd.show_osd(f"Subtitle Sync: {offset:+.1f}s")
            elif ctrl and alt:
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

        # Up / Down Volume & Shift+Up/Down Volume Boost (PreAmp) & Alt+Up/Down Subtitle Pos
        if keyval in (Gdk.KEY_Up, Gdk.KEY_KP_Up):
            if alt and not (ctrl or shift):
                pos = self.core.adjust_subtitle_pos(-2)
                self.osd.show_osd(f"Subtitle Position: {pos}%")
            elif shift:
                self.dsp.audio_boost_db = min(24.0, self.dsp.audio_boost_db + 1.0)
                self.apply_audio_filters()
                self.osd.show_osd(f"Audio Boost PreAmp: +{self.dsp.audio_boost_db:.1f} dB")
            else:
                self.core.adjust_volume(+2.0)
                self.osd.show_osd(f"Volume: {int(self.core.volume)}%")
            return True

        if keyval in (Gdk.KEY_Down, Gdk.KEY_KP_Down):
            if alt and not (ctrl or shift):
                pos = self.core.adjust_subtitle_pos(+2)
                self.osd.show_osd(f"Subtitle Position: {pos}%")
            elif shift:
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

        # Shift+E: Toggle Audio Enhancement (loudness & speech boost)
        if shift and keyval in (Gdk.KEY_e, Gdk.KEY_E) and not (ctrl or alt):
            self.toggle_audio_enhancement()
            return True

        # Audio Track & Audio Sync
        if keyval in (Gdk.KEY_a, Gdk.KEY_A) and not ctrl:
            self.core.cycle_audio_track()
            self.osd.show_osd("Audio Track Cycled")
            return True
        if shift and keyval == Gdk.KEY_bracketleft:
            new_delay = round(self.core.audio_delay_sec - 0.05, 3)
            self.core.set_audio_delay(new_delay)
            self.osd.show_osd(f"Audio Sync: {new_delay * 1000:+.0f} ms")
            return True
        if shift and keyval == Gdk.KEY_bracketright:
            new_delay = round(self.core.audio_delay_sec + 0.05, 3)
            self.core.set_audio_delay(new_delay)
            self.osd.show_osd(f"Audio Sync: {new_delay * 1000:+.0f} ms")
            return True
        if shift and keyval == Gdk.KEY_backslash:
            self.core.set_audio_delay(0.0)
            self.osd.show_osd("Audio Sync: 0.0s (Reset)")
            return True

        # Subtitle Sync: [ / ] (-0.5s / +0.5s per README)
        if not (ctrl or alt or shift) and keyval == Gdk.KEY_bracketleft:
            offset = self.sub_mgr.adjust_sync(-0.5)
            self.core.set_subtitle_delay(offset)
            self.osd.show_osd(f"Subtitle Sync: {offset:+.1f}s")
            return True
        if not (ctrl or alt or shift) and keyval == Gdk.KEY_bracketright:
            offset = self.sub_mgr.adjust_sync(+0.5)
            self.core.set_subtitle_delay(offset)
            self.osd.show_osd(f"Subtitle Sync: {offset:+.1f}s")
            return True
        if not (ctrl or alt or shift) and keyval == Gdk.KEY_backslash:
            self.sub_mgr.reset_sync()
            self.core.set_subtitle_delay(0.0)
            self.osd.show_osd("Subtitle Sync: 0.0s (Reset)")
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
        if shift and not (ctrl or alt) and keyval in (Gdk.KEY_Page_Down, Gdk.KEY_KP_Page_Down):
            self.handle_command("CMD_CHAPTER_NEXT")
            return True
        if shift and not (ctrl or alt) and keyval in (Gdk.KEY_Page_Up, Gdk.KEY_KP_Page_Up):
            self.handle_command("CMD_CHAPTER_PREV")
            return True
        if not (ctrl or alt or shift) and keyval in (Gdk.KEY_Page_Down, Gdk.KEY_KP_Page_Down):
            self.play_next()
            return True
        if not (ctrl or alt or shift) and keyval in (Gdk.KEY_Page_Up, Gdk.KEY_KP_Page_Up):
            self.play_prev()
            return True
        if alt and keyval in (Gdk.KEY_Up, Gdk.KEY_KP_Up):
            pos = self.core.adjust_subtitle_pos(-2)
            self.sub_mgr.style.pos = pos
            self.sub_mgr.save_style_config()
            self.osd.show_osd(f"Subtitle Position: {pos}%")
            return True
        if alt and keyval in (Gdk.KEY_Down, Gdk.KEY_KP_Down):
            pos = self.core.adjust_subtitle_pos(+2)
            self.sub_mgr.style.pos = pos
            self.sub_mgr.save_style_config()
            self.osd.show_osd(f"Subtitle Position: {pos}%")
            return True
        if alt and keyval in (Gdk.KEY_Home, Gdk.KEY_KP_Home):
            self.core.set_property("sub-pos", "100")
            self.core.sub_pos = 100
            self.sub_mgr.style.pos = 100
            self.sub_mgr.save_style_config()
            self.osd.show_osd("Subtitle Position: Default (100%)")
            return True
        if alt and not ctrl and keyval in (Gdk.KEY_e, Gdk.KEY_E):
            self.show_subtitle_style_dialog()
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
            self._is_keep_above = not getattr(self, "_is_keep_above", False)
            self.set_keep_above(self._is_keep_above)
            self.osd.show_osd(f"Stay on Top: {'ON' if self._is_keep_above else 'OFF'}")
            return True
        if alt and keyval in (Gdk.KEY_1, Gdk.KEY_KP_1):
            w = int(self.core.video_width * 0.5) if self.core.video_width > 0 else 640
            h = int(self.core.video_height * 0.5 + 62) if self.core.video_height > 0 else 360
            self._resize_clamped(w, h)
            self.osd.show_osd("Window Size: 50% (0.5x)")
            return True
        if alt and keyval in (Gdk.KEY_2, Gdk.KEY_KP_2):
            w = self.core.video_width if self.core.video_width > 0 else 960
            h = (self.core.video_height + 62) if self.core.video_height > 0 else 580
            self._resize_clamped(w, h)
            self.osd.show_osd("Window Size: 100% (Original Size)")
            return True
        if alt and keyval in (Gdk.KEY_3, Gdk.KEY_KP_3):
            w = int(self.core.video_width * 1.5) if self.core.video_width > 0 else 1280
            h = int(self.core.video_height * 1.5 + 62) if self.core.video_height > 0 else 720
            self._resize_clamped(w, h)
            self.osd.show_osd("Window Size: 150% (1.5x)")
            return True
        if alt and keyval in (Gdk.KEY_4, Gdk.KEY_KP_4):
            w = int(self.core.video_width * 2.0) if self.core.video_width > 0 else 1920
            h = int(self.core.video_height * 2.0 + 62) if self.core.video_height > 0 else 1080
            self._resize_clamped(w, h)
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
        if not (ctrl or alt or shift) and keyval in (Gdk.KEY_m, Gdk.KEY_M):
            self.core.toggle_mute()
            self._save_audio_settings()
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

        # A-B Repeat: Ctrl+[, Ctrl+], Ctrl+\
        if ctrl and keyval == Gdk.KEY_bracketleft:
            self.set_repeat_a()
            return True
        if ctrl and keyval == Gdk.KEY_bracketright:
            self.set_repeat_b()
            return True
        if ctrl and keyval == Gdk.KEY_backslash:
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
            self.osd_layer.queue_draw()
            return True

        # Function Keys: F1 (About / Ctrl+F1: Media Info), F4 (Close), F5 (Prefs), F6 (Control Box), F7 (Equalizer), F8/F12 (Playlist)
        if keyval == Gdk.KEY_F1:
            if ctrl:
                self.show_media_info_dialog()
            else:
                self.handle_command("CMD_ABOUT_DIALOG")
            return True
        if keyval == Gdk.KEY_F4 and not alt:
            self.handle_command("CMD_MEDIA_CLOSE")
            return True
        if keyval in (Gdk.KEY_F5, Gdk.KEY_F6):
            if self.control_box.get_visible():
                self.control_box.hide()
            else:
                self.control_box.show_all()
            return True
        if keyval == Gdk.KEY_F7:
            if self.control_box.get_visible() and self.control_box.notebook.get_current_page() == 0:
                self.control_box.hide()
            else:
                self.control_box.show_all()
                if hasattr(self.control_box, "select_tab"):
                    self.control_box.select_tab(0)
            return True
        if keyval in (Gdk.KEY_F8, Gdk.KEY_F12):
            if self.playlist_window.get_visible():
                self.playlist_window.hide()
            else:
                self.playlist_window.show_all()
            return True

        # Capture: Ctrl+P (Snapshot), Ctrl+E (Save Frame As), Ctrl+C (Copy Frame), Ctrl+Alt+G (GIF), Ctrl+Alt+S (Search Subtitles Online)
        if ctrl and not alt and keyval in (Gdk.KEY_p, Gdk.KEY_P):
            self.handle_command("CMD_CAPTURE_FRAME")
            return True
        if ctrl and not alt and keyval in (Gdk.KEY_e, Gdk.KEY_E):
            self.handle_command("CMD_CAPTURE_FRAME_AS")
            return True
        if ctrl and not alt and keyval in (Gdk.KEY_c, Gdk.KEY_C):
            self.handle_command("CMD_CAPTURE_TO_CLIPBOARD")
            return True
        if ctrl and alt and keyval in (Gdk.KEY_g, Gdk.KEY_G):
            self.handle_command("CMD_CREATE_GIF")
            return True
        if ctrl and alt and keyval in (Gdk.KEY_s, Gdk.KEY_S):
            self.handle_command("CMD_SUB_ONLINE_SEARCH")
            return True

        # Additional Documented Shortcuts: Ctrl+F11 (Deinterlace), Ctrl+H (HDR), Ctrl+S (Screen Capture), Ctrl+J (Webcam)
        if ctrl and keyval == Gdk.KEY_F11:
            self.handle_command("CMD_DEINTERLACE_TOGGLE")
            return True
        if ctrl and not alt and keyval in (Gdk.KEY_h, Gdk.KEY_H):
            self.handle_command("CMD_TOGGLE_HDR")
            return True
        if ctrl and not alt and not shift and keyval in (Gdk.KEY_s, Gdk.KEY_S):
            self.handle_command("CMD_OPEN_SCREEN_CAPTURE")
            return True
        if ctrl and not alt and keyval in (Gdk.KEY_j, Gdk.KEY_J):
            self.handle_command("CMD_OPEN_WEBCAM")
            return True

        # Colors: Q (Reset), W/E (Brightness), R/T (Contrast), Y/U (Saturation), I/O (Hue)
        if keyval in (Gdk.KEY_q, Gdk.KEY_Q) and not (ctrl or alt):
            self.shader_mgr.reset_colors()
            self.core.set_video_colors(0, 0, 0, 0, 0)
            self.osd.show_osd("Video Colors: Reset")
            return True
        if keyval in (Gdk.KEY_w, Gdk.KEY_W) and not (ctrl or alt):
            self.shader_mgr.brightness = max(-100, self.shader_mgr.brightness - 1)
            self.core.set_video_colors(self.shader_mgr.brightness, self.shader_mgr.contrast, self.shader_mgr.saturation, self.shader_mgr.hue, 0)
            self.osd.show_osd(f"Brightness: {self.shader_mgr.brightness}%")
            return True
        if keyval in (Gdk.KEY_e, Gdk.KEY_E) and not (ctrl or alt):
            self.shader_mgr.brightness = min(100, self.shader_mgr.brightness + 1)
            self.core.set_video_colors(self.shader_mgr.brightness, self.shader_mgr.contrast, self.shader_mgr.saturation, self.shader_mgr.hue, 0)
            self.osd.show_osd(f"Brightness: {self.shader_mgr.brightness}%")
            return True
        if keyval in (Gdk.KEY_r, Gdk.KEY_R) and not (ctrl or alt):
            self.shader_mgr.contrast = max(-100, self.shader_mgr.contrast - 1)
            self.core.set_video_colors(self.shader_mgr.brightness, self.shader_mgr.contrast, self.shader_mgr.saturation, self.shader_mgr.hue, 0)
            self.osd.show_osd(f"Contrast: {self.shader_mgr.contrast}%")
            return True
        if keyval in (Gdk.KEY_t, Gdk.KEY_T) and not (ctrl or alt):
            self.shader_mgr.contrast = min(100, self.shader_mgr.contrast + 1)
            self.core.set_video_colors(self.shader_mgr.brightness, self.shader_mgr.contrast, self.shader_mgr.saturation, self.shader_mgr.hue, 0)
            self.osd.show_osd(f"Contrast: {self.shader_mgr.contrast}%")
            return True
        if keyval in (Gdk.KEY_y, Gdk.KEY_Y) and not (ctrl or alt):
            self.shader_mgr.saturation = max(-100, self.shader_mgr.saturation - 1)
            self.core.set_video_colors(self.shader_mgr.brightness, self.shader_mgr.contrast, self.shader_mgr.saturation, self.shader_mgr.hue, 0)
            self.osd.show_osd(f"Saturation: {self.shader_mgr.saturation}%")
            return True
        if keyval in (Gdk.KEY_u, Gdk.KEY_U) and not (ctrl or alt):
            self.shader_mgr.saturation = min(100, self.shader_mgr.saturation + 1)
            self.core.set_video_colors(self.shader_mgr.brightness, self.shader_mgr.contrast, self.shader_mgr.saturation, self.shader_mgr.hue, 0)
            self.osd.show_osd(f"Saturation: {self.shader_mgr.saturation}%")
            return True
        if keyval in (Gdk.KEY_i, Gdk.KEY_I) and not (ctrl or alt):
            self.shader_mgr.hue = max(-100, self.shader_mgr.hue - 1)
            self.core.set_video_colors(self.shader_mgr.brightness, self.shader_mgr.contrast, self.shader_mgr.saturation, self.shader_mgr.hue, 0)
            self.osd.show_osd(f"Hue: {self.shader_mgr.hue}%")
            return True
        if keyval in (Gdk.KEY_o, Gdk.KEY_O) and not (ctrl or alt):
            self.shader_mgr.hue = min(100, self.shader_mgr.hue + 1)
            self.core.set_video_colors(self.shader_mgr.brightness, self.shader_mgr.contrast, self.shader_mgr.saturation, self.shader_mgr.hue, 0)
            self.osd.show_osd(f"Hue: {self.shader_mgr.hue}%")
            return True

        return False

    # --- Command Dispatcher ---

    def handle_command(self, cmd_id: str, arg: Any = None) -> None:
        if cmd_id in ("CMD_MEDIA_PLAY", "CMD_MEDIA_PAUSE", "CMD_MEDIA_PLAY_PAUSE"):
            self.core.play_pause()
        elif cmd_id == "CMD_MEDIA_CLOSE":
            self._save_current_position()
            self.core.stop()
            self.set_title("Jonaki")
            if hasattr(self, "torrent_manager") and self.torrent_manager:
                self.torrent_manager.stop_session()
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
        elif cmd_id == "CMD_OPEN_CONTAINING_FOLDER":
            cur_f = self.core.current_file
            if cur_f and os.path.exists(cur_f):
                folder = os.path.dirname(os.path.abspath(cur_f))
                import subprocess
                try:
                    subprocess.Popen(["xdg-open", folder])
                except Exception as e:
                    print(f"[Jonaki] Failed to open folder: {e}")
        elif cmd_id == "CMD_OPEN_URL":
            self._open_url_dialog()
        elif cmd_id in ("CMD_OPEN_TORRENT", "ID_OPEN_TORRENT"):
            self._open_torrent_dialog()
        elif cmd_id == "CMD_OPEN_SCREEN_CAPTURE":
            disp = os.environ.get("DISPLAY", ":0.0")
            if ":" in disp and "." not in disp.split(":")[-1]:
                disp = f"{disp}.0"
            self.play_file(f"av://x11grab:{disp}")
            self.osd.show_osd("Screen Capture Device")
        elif cmd_id == "CMD_OPEN_WEBCAM":
            self.play_file("av://v4l2:/dev/video0")
            self.osd.show_osd("Webcam Device")
        elif cmd_id == "CMD_OPEN_SPECIFIC_FILE":
            if arg:
                self.add_files_to_playlist([arg], auto_play=True, clear_existing=True)
        elif cmd_id == "CMD_SET_CHAPTER":
            if arg is not None:
                self.core.set_chapter(int(arg))
                chs = self.core.get_chapters()
                idx = int(arg)
                title = chs[idx].get("title") if 0 <= idx < len(chs) else f"Chapter {idx + 1}"
                self.osd.show_osd(f"Chapter: {title}")
        elif cmd_id == "CMD_CHAPTER_PREV":
            self.core.prev_chapter()
            cur_idx = self.core.get_current_chapter()
            chs = self.core.get_chapters()
            title = chs[cur_idx].get("title") if 0 <= cur_idx < len(chs) else "Previous Chapter"
            self.osd.show_osd(f"Chapter: {title}")
        elif cmd_id == "CMD_CHAPTER_NEXT":
            self.core.next_chapter()
            cur_idx = self.core.get_current_chapter()
            chs = self.core.get_chapters()
            title = chs[cur_idx].get("title") if 0 <= cur_idx < len(chs) else "Next Chapter"
            self.osd.show_osd(f"Chapter: {title}")
        elif cmd_id == "CMD_CLEAR_RECENT_FILES":
            self.db.clear_history()
            self.osd.show_osd("Recent Files Cleared")
        elif cmd_id == "CMD_FULLSCREEN":
            self.toggle_fullscreen()
        elif cmd_id == "CMD_VIDEO_STRETCH":
            mode_str = self.core.toggle_stretch()
            self.osd.show_osd(f"Video Fit: {mode_str}")
        elif cmd_id == "CMD_VIDEO_SCALE_HEIGHT_UP":
            val = self.core.scale_video_height(+0.05)
            self.osd.show_osd(f"Video Height: {int(round(val * 100))}%")
        elif cmd_id == "CMD_VIDEO_SCALE_HEIGHT_DOWN":
            val = self.core.scale_video_height(-0.05)
            self.osd.show_osd(f"Video Height: {int(round(val * 100))}%")
        elif cmd_id == "CMD_VIDEO_SCALE_WIDTH_UP":
            val = self.core.scale_video_width(+0.05)
            self.osd.show_osd(f"Video Width: {int(round(val * 100))}%")
        elif cmd_id == "CMD_VIDEO_SCALE_WIDTH_DOWN":
            val = self.core.scale_video_width(-0.05)
            self.osd.show_osd(f"Video Width: {int(round(val * 100))}%")
        elif cmd_id == "CMD_VIDEO_SCALE_RESET":
            self.core.reset_video_dimensions()
            self.osd.show_osd("Video Dimensions: Reset (100%)")
        elif cmd_id == "CMD_VIDEO_ZOOM_IN":
            val = self.core.zoom_video(+0.05)
            self.osd.show_osd(f"Video Zoom: {int(round(val * 100))}%")
        elif cmd_id == "CMD_VIDEO_ZOOM_OUT":
            val = self.core.zoom_video(-0.05)
            self.osd.show_osd(f"Video Zoom: {int(round(val * 100))}%")
        elif cmd_id in ("CMD_CONTROL_BOX", "ID_CONTROL_BOX_WINDOW", "CMD_PREFERENCES_DIALOG", "CMD_EQUALIZER_DIALOG"):
            self.control_box.show_all()
        elif cmd_id in ("CMD_PLAYLIST_WINDOW", "ID_PLAYLIST_WINDOW"):
            self.playlist_window.show_all()
        elif cmd_id == "CMD_POPUPMENU_STREAM_SELECT":
            self._open_url_dialog()
        elif cmd_id == "CMD_OSD_PLAYINFO":
            self.osd.toggle_tech_info()
            self.osd_layer.queue_draw()
        elif cmd_id == "CMD_VIDEO_CODEC_FOURCC_MESSAGE":
            self.show_media_info_dialog()
        elif cmd_id == "CMD_AUDIO_CODEC_TYPE_MESSAGE":
            self.core.cycle_audio_track()
            aid = self.core.get_property("aid")
            self.osd.show_osd(f"Audio Track Cycled (#{aid})" if aid and aid != "no" else "Audio Track: Off")
        elif cmd_id == "CMD_AUDIO_OUT_NUM_CHANNEL_MESSAGE":
            self.control_box.notebook.set_current_page(0)
            self.control_box.show_all()
        elif cmd_id in ("CMD_TOGGLE_ALWAYS_ON_TOP", "ID_ETC_NEXTONTOP"):
            self._is_keep_above = not getattr(self, "_is_keep_above", False)
            self.set_keep_above(self._is_keep_above)
            self.osd.show_osd(f"Stay on Top: {'ON' if self._is_keep_above else 'OFF'}")
            if hasattr(self, "top_bar") and self.top_bar:
                self.top_bar.queue_draw()
        elif cmd_id == "CMD_MIN_WINDOW":
            self.iconify()
        elif cmd_id == "CMD_CLEAR_PLAYLIST":
            self.playlist.clear()
            self.current_index = -1
            self.core.stop()
            self.playlist_window.update_playlist(self.playlist)
            self.osd.show_osd("Playlist Cleared")
        elif cmd_id == "CMD_WINDOW_SIZE_50":
            w = int(self.core.video_width * 0.5) if self.core.video_width > 0 else 640
            h = int(self.core.video_height * 0.5 + 62) if self.core.video_height > 0 else 360
            self._resize_clamped(w, h)
            self.osd.show_osd("Window Size: 50% (0.5x)")
        elif cmd_id == "CMD_WINDOW_SIZE_100":
            w = self.core.video_width if self.core.video_width > 0 else 960
            h = (self.core.video_height + 62) if self.core.video_height > 0 else 580
            self._resize_clamped(w, h)
            self.osd.show_osd("Window Size: 100% (Original Size)")
        elif cmd_id == "CMD_WINDOW_SIZE_150":
            w = int(self.core.video_width * 1.5) if self.core.video_width > 0 else 1280
            h = int(self.core.video_height * 1.5 + 62) if self.core.video_height > 0 else 720
            self._resize_clamped(w, h)
            self.osd.show_osd("Window Size: 150% (1.5x)")
        elif cmd_id == "CMD_WINDOW_SIZE_200":
            w = int(self.core.video_width * 2.0) if self.core.video_width > 0 else 1920
            h = int(self.core.video_height * 2.0 + 62) if self.core.video_height > 0 else 1080
            self._resize_clamped(w, h)
            self.osd.show_osd("Window Size: 200% (2.0x)")
        elif cmd_id == "CMD_REPEAT_SET_A":
            self.set_repeat_a()
        elif cmd_id == "CMD_REPEAT_SET_B":
            self.set_repeat_b()
        elif cmd_id == "CMD_REPEAT_CLEAR":
            self.core.clear_repeat()
            self.osd.show_osd("A-B Repeat Cleared")
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
            self.core.set_glsl_shaders(self.shader_mgr.get_glsl_shaders_string())
            self.osd.show_osd("Pixel Shader: Sharpen 3x3")
        elif cmd_id == "CMD_SHADER_ADAPTIVE_SHARPEN":
            self.shader_mgr.enable_shader("adaptive_sharpen.hook")
            self.core.set_glsl_shaders(self.shader_mgr.get_glsl_shaders_string())
            self.osd.show_osd("Pixel Shader: Adaptive Sharpen")
        elif cmd_id == "CMD_SHADER_DENOISE":
            self.shader_mgr.enable_shader("denoise.hook")
            self.core.set_glsl_shaders(self.shader_mgr.get_glsl_shaders_string())
            self.osd.show_osd("Pixel Shader: Denoise")
        elif cmd_id == "CMD_SHADER_CLEAR":
            self.shader_mgr.active_shaders.clear()
            self.core.set_glsl_shaders(self.shader_mgr.get_glsl_shaders_string())
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
        elif cmd_id == "CMD_AUDIO_ENHANCE_TOGGLE":
            self.toggle_audio_enhancement()
        elif cmd_id.startswith("CMD_AUDIO_ENHANCE_PRESET_"):
            preset_name = cmd_id.replace("CMD_AUDIO_ENHANCE_PRESET_", "").replace("_", " ")
            self.set_audio_enhancement_preset(preset_name)
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
        elif cmd_id == "CMD_SUB_STYLE_SETTINGS":
            self.show_subtitle_style_dialog()
        elif cmd_id == "CMD_SUB_ONLINE_SEARCH":
            self.show_subtitle_search_dialog()
        elif cmd_id == "CMD_CAPTURE_FRAME":
            if not self.core.current_file:
                self.osd.show_osd("Capture Failed: No active media")
            else:
                fn = self.capture_mgr.generate_capture_filename()
                if self.core.take_screenshot(fn):
                    self.osd.show_osd(f"Snapshot Saved: {os.path.basename(fn)}")
                else:
                    self.osd.show_osd("Capture Failed")
        elif cmd_id == "CMD_CAPTURE_FRAME_AS":
            if not self.core.current_file:
                self.osd.show_osd("Capture Failed: No active media")
            else:
                self._save_frame_as_dialog()
        elif cmd_id == "CMD_CAPTURE_TO_CLIPBOARD":
            if not self.core.current_file:
                self.osd.show_osd("Capture Failed: No active media")
            else:
                fn = self.capture_mgr.generate_capture_filename()
                if self.core.take_screenshot(fn):
                    self.capture_mgr.copy_file_to_clipboard(fn)
                    self.osd.show_osd("Snapshot Copied to Clipboard")
                else:
                    self.osd.show_osd("Capture Failed")
        elif cmd_id == "CMD_CREATE_GIF":
            if not self.core.current_file:
                self.osd.show_osd("GIF Creation Failed: No active media")
            else:
                cur_f = self.core.current_file
                pos = self.core.position
                self.osd.show_osd("Creating Animated GIF...")
                def _worker_gif():
                    gif_path = self.capture_mgr.create_animated_gif(cur_f, pos, 5.0)
                    if gif_path:
                        GLib.idle_add(lambda: self.osd.show_osd(f"GIF Created: {os.path.basename(gif_path)}"))
                    else:
                        GLib.idle_add(lambda: self.osd.show_osd("Failed to create GIF"))
                threading.Thread(target=_worker_gif, daemon=True).start()
        elif cmd_id == "CMD_CREATE_STORYBOARD":
            if not self.core.current_file:
                self.osd.show_osd("Storyboard Failed: No active media")
            else:
                cur_f = self.core.current_file
                dur = self.core.duration
                self.osd.show_osd("Creating Storyboard...")
                def _worker_sb():
                    sb_path = self.capture_mgr.create_storyboard(cur_f, dur)
                    if sb_path:
                        GLib.idle_add(lambda: self.osd.show_osd(f"Storyboard Created: {os.path.basename(sb_path)}"))
                    else:
                        GLib.idle_add(lambda: self.osd.show_osd("Failed to create Storyboard"))
                threading.Thread(target=_worker_sb, daemon=True).start()
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
            label = "Auto (Default)" if str(arg) == "-1" else str(arg)
            self.osd.show_osd(f"Aspect Ratio: {label}")
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
            self.sub_mgr.style.pos = pos
            self.sub_mgr.save_style_config()
            self.osd.show_osd(f"Subtitle Position: {pos}%")
        elif cmd_id == "CMD_SUB_POS_DOWN":
            pos = self.core.adjust_subtitle_pos(+2)
            self.sub_mgr.style.pos = pos
            self.sub_mgr.save_style_config()
            self.osd.show_osd(f"Subtitle Position: {pos}%")
        elif cmd_id == "CMD_SUB_POS_RESET":
            self.core.set_property("sub-pos", "100")
            self.core.sub_pos = 100
            self.sub_mgr.style.pos = 100
            self.sub_mgr.save_style_config()
            self.osd.show_osd("Subtitle Position: Default (100%)")
        elif cmd_id == "CMD_SUB_SIZE_UP":
            sz = self.sub_mgr.increase_font_size(2)
            self.core.set_subtitle_font_size(sz)
            self.sub_mgr.save_style_config()
            self.osd.show_osd(f"Subtitle Size: {sz} pt")
        elif cmd_id == "CMD_SUB_SIZE_DOWN":
            sz = self.sub_mgr.decrease_font_size(2)
            self.core.set_subtitle_font_size(sz)
            self.sub_mgr.save_style_config()
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

    def _resize_clamped(self, w: int, h: int) -> None:
        screen = self.get_screen()
        if screen:
            try:
                display = screen.get_display()
                monitor = display.get_primary_monitor() or display.get_monitor(0)
                geom = monitor.get_geometry()
                sw, sh = geom.width, geom.height
            except Exception:
                sw, sh = screen.get_width(), screen.get_height()
            max_w = max(400, sw - 40)
            max_h = max(300, sh - 80)
            if w > max_w or h > max_h:
                aspect = w / max(1, h)
                if w / max_w > h / max_h:
                    w = max_w
                    h = int(w / aspect)
                else:
                    h = max_h
                    w = int(h * aspect)
        self.resize(max(320, int(w)), max(240, int(h)))

    def apply_subtitle_style(self) -> None:
        """Applies configured subtitle styles to the playback engine."""
        if hasattr(self, "sub_mgr") and hasattr(self, "core"):
            self.core.apply_subtitle_style(self.sub_mgr.style)

    def show_subtitle_style_dialog(self) -> None:
        """Opens the PotPlayer-like Subtitle Style Settings dialog."""
        def _on_style_updated(new_style):
            self.sub_mgr.style = new_style
            self.sub_mgr.save_style_config()
            self.apply_subtitle_style()
            self.osd.show_osd("Subtitle Style Updated")

        dialog = SubtitleStyleDialog(self, self.sub_mgr.style, _on_style_updated)
        dialog.show_all()

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
            if hasattr(self, "top_bar") and self.top_bar:
                self.top_bar.hide()
            self.skin_area.show()
            self._controls_visible = True
            self._set_cursor_visible(True)
        else:
            self.fullscreen()
            self.is_fullscreen = True
            self.skin_area.show()
            if hasattr(self, "top_bar") and self.top_bar:
                self.top_bar.show()
            self._controls_visible = True
            self._last_mouse_move_time = time.time()
            self._set_cursor_visible(True)

    def _on_window_state_event(self, widget, event):
        is_fs = bool(event.new_window_state & Gdk.WindowState.FULLSCREEN)
        if self.is_fullscreen != is_fs:
            self.is_fullscreen = is_fs
            if not self.is_fullscreen:
                if hasattr(self, "top_bar") and self.top_bar:
                    self.top_bar.hide()
                self.skin_area.show()
                self._controls_visible = True
                self._set_cursor_visible(True)
            else:
                self.skin_area.show()
                if hasattr(self, "top_bar") and self.top_bar:
                    self.top_bar.show()
                self._controls_visible = True
                self._last_mouse_move_time = time.time()
                self._set_cursor_visible(True)
        return False

    # --- Core Event Callbacks ---

    def _on_core_time_update(self, pos: float, dur: float):
        if self.skin.volume_slider:
            self.skin.volume_slider.value = self.core.volume / 100.0
        if dur > 0 and 0 <= self.current_index < len(self.playlist):
            item = self.playlist[self.current_index]
            if item.get("duration", 0.0) <= 0.0 or abs(item.get("duration", 0.0) - dur) > 1.0:
                item["duration"] = dur
                self.playlist_window.update_playlist(self.playlist)

    def _on_core_state_change(self, state: str):
        self.skin_area.queue_draw()
        if hasattr(self, "power_inhibitor") and self.power_inhibitor:
            is_playing = (state == PlaybackState.PLAYING)
            self.power_inhibitor.update_state(is_playing)
        if hasattr(self, "mpris") and self.mpris:
            self.mpris.notify_playback_changed()

    def _on_core_file_end(self):
        if self.core.current_file:
            try:
                kwargs = {
                    "duration": getattr(self.core, "duration", 0.0),
                    "title": self.core.current_title or os.path.basename(self.core.current_file)
                }
                aid = self.core.get_property("aid") if hasattr(self.core, "get_property") else None
                sid = self.core.get_property("sid") if hasattr(self.core, "get_property") else None
                vol = getattr(self.core, "volume", None)
                if isinstance(aid, str) and aid and aid != "no":
                    kwargs["audio_track"] = aid
                if isinstance(sid, str) and sid and sid != "no":
                    kwargs["subtitle_track"] = sid
                if isinstance(vol, (int, float)):
                    kwargs["volume"] = float(vol)

                self.db.save_playback_position(
                    self.core.current_file,
                    self.core.position,
                    **kwargs
                )
            except Exception as e:
                print(f"[MediaDB] Failed to save resume position on file end: {e}")

        # Auto-play next in playlist
        if self.current_index + 1 < len(self.playlist):
            self.play_index(self.current_index + 1)
        elif hasattr(self, "mpris") and self.mpris:
            self.mpris.notify_playback_changed()

    # --- Playlist & Playback Management ---

    def add_files_to_playlist(self, file_paths: List[str], auto_play: bool = False, clear_existing: bool = False,
                               seek_pts: float = 0.0, sub_file: Optional[str] = None, audio_file: Optional[str] = None) -> None:
        if clear_existing:
            self.playlist.clear()
            self.current_index = -1

        start_index = len(self.playlist)
        for fp in file_paths:
            clean_fp = normalize_media_path(fp)
            self.playlist.append({
                "path": clean_fp,
                "title": os.path.basename(clean_fp),
                "duration": 0.0
            })
        self.playlist_window.update_playlist(self.playlist)
        try:
            self.db.save_playlist(self.playlist)
        except Exception as e:
            print(f"[MediaDB] Failed to save playlist: {e}")

        if auto_play and len(self.playlist) > 0:
            target_index = start_index if start_index < len(self.playlist) else 0
            self.play_index(target_index, seek_pts=seek_pts, sub_file=sub_file, audio_file=audio_file)

    def _save_audio_settings(self) -> None:
        try:
            vol = getattr(self.core, "volume", None)
            if isinstance(vol, (int, float)):
                self.db.set_setting("master_volume", str(round(vol, 1)))
            is_muted = getattr(self.core, "is_muted", False)
            if isinstance(is_muted, bool):
                self.db.set_setting("master_muted", "1" if is_muted else "0")
        except Exception as e:
            print(f"[MediaDB] Failed to save audio settings: {e}")

    def _save_current_position(self) -> None:
        pos = getattr(self.core, "position", None)
        if self.core.current_file and isinstance(pos, (int, float)) and pos > 5.0:
            try:
                kwargs = {
                    "duration": getattr(self.core, "duration", 0.0),
                    "title": self.core.current_title or os.path.basename(self.core.current_file)
                }
                aid = self.core.get_property("aid") if hasattr(self.core, "get_property") else None
                sid = self.core.get_property("sid") if hasattr(self.core, "get_property") else None
                vol = getattr(self.core, "volume", None)
                if isinstance(aid, str) and aid and aid != "no":
                    kwargs["audio_track"] = aid
                if isinstance(sid, str) and sid and sid != "no":
                    kwargs["subtitle_track"] = sid
                if isinstance(vol, (int, float)):
                    kwargs["volume"] = float(vol)

                self.db.save_playback_position(
                    self.core.current_file,
                    pos,
                    **kwargs
                )
            except Exception as e:
                print(f"[MediaDB] Failed to save playback position: {e}")
        self._save_audio_settings()

    def play_index(self, index: int, seek_pts: float = 0.0, sub_file: Optional[str] = None, audio_file: Optional[str] = None) -> None:
        if 0 <= index < len(self.playlist):
            self._save_current_position()
            self.current_index = index
            self.playlist_window.update_playlist(self.playlist)
            item = self.playlist[index]
            self.play_file(item["path"], seek_pts=seek_pts, sub_file=sub_file, audio_file=audio_file)

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
        if not self.core.current_file and len(self.playlist) > 0:
            self.play_index(max(0, self.current_index))
            return
        self.core.play_pause()

    def remove_from_playlist(self, index: int) -> None:
        if 0 <= index < len(self.playlist):
            self.playlist.pop(index)
            if index == self.current_index:
                if len(self.playlist) > 0:
                    new_idx = min(index, len(self.playlist) - 1)
                    self.play_index(new_idx)
                else:
                    self._save_current_position()
                    self.core.stop()
                    self.set_title("Jonaki")
                    self.current_index = -1
            elif index < self.current_index:
                self.current_index -= 1
            self.playlist_window.update_playlist(self.playlist)
            try:
                self.db.save_playlist(self.playlist)
            except Exception as e:
                print(f"[MediaDB] Failed to save playlist: {e}")

    def sort_playlist(self) -> None:
        cur_path = self.playlist[self.current_index]["path"] if 0 <= self.current_index < len(self.playlist) else None
        self.playlist.sort(key=lambda x: (x.get("title") or os.path.basename(x["path"])).lower())
        if cur_path:
            for i, it in enumerate(self.playlist):
                if it["path"] == cur_path:
                    self.current_index = i
                    break
        self.playlist_window.update_playlist(self.playlist)
        try:
            self.db.save_playlist(self.playlist)
        except Exception as e:
            print(f"[MediaDB] Failed to save playlist: {e}")

    def shuffle_playlist(self) -> None:
        cur_path = self.playlist[self.current_index]["path"] if 0 <= self.current_index < len(self.playlist) else None
        random.shuffle(self.playlist)
        if cur_path:
            for i, it in enumerate(self.playlist):
                if it["path"] == cur_path:
                    self.current_index = i
                    break
        self.playlist_window.update_playlist(self.playlist)
        try:
            self.db.save_playlist(self.playlist)
        except Exception as e:
            print(f"[MediaDB] Failed to save playlist: {e}")

    def set_subtitle_size(self, size_pt: int) -> None:
        self.sub_mgr.font_size = size_pt
        self.core.set_subtitle_font_size(size_pt)
        self.osd.show_osd(f"Subtitle Size: {size_pt} pt")

    def set_subtitle_sync(self, offset_sec: float) -> None:
        self.sub_mgr.sync_offset_sec = offset_sec
        self.core.set_subtitle_delay(offset_sec)
        self.osd.show_osd(f"Subtitle Sync: {offset_sec:+.1f}s")

    def toggle_translation(self, active: bool) -> None:
        self.sub_mgr.translation_enabled = active
        self.osd.show_osd(f"AI Subtitle Translation: {'ON' if active else 'OFF'}")

    def play_file(self, file_path: str, seek_pts: float = 0.0, sub_file: Optional[str] = None, audio_file: Optional[str] = None) -> None:
        file_path = normalize_media_path(file_path)
        if file_path.startswith("magnet:") or file_path.lower().endswith(".torrent"):
            self._open_torrent_dialog(initial_source=file_path)
            return

        if hasattr(self, "torrent_manager") and self.torrent_manager and self.torrent_manager.is_streaming:
            if file_path != self.torrent_manager.stream_url:
                self.torrent_manager.stop_session()

        if self.core.wid is None:
            self._pending_playback = (file_path, seek_pts, sub_file, audio_file)
            self.set_title(f"Jonaki - {os.path.basename(file_path)}")
            return

        saved_entry = self.db.get_playback_entry(file_path)
        if saved_entry:
            if seek_pts <= 0.0:
                saved_pts = saved_entry.get("last_position")
                if saved_pts is not None and saved_pts > 5.0 and not saved_entry.get("completed", 0):
                    seek_pts = saved_pts
                    self.osd.show_osd(f"Resumed at {self.skin._format_time(saved_pts)}")
        elif seek_pts <= 0.0:
            saved_pts = self.db.get_playback_position(file_path)
            if saved_pts is not None and saved_pts > 5.0:
                seek_pts = saved_pts
                self.osd.show_osd(f"Resumed at {self.skin._format_time(saved_pts)}")

        self.core.load_file(file_path, start_pts=seek_pts, sub_file=sub_file, audio_file=audio_file)
        self.set_title(f"Jonaki - {os.path.basename(file_path)}")
        self.apply_audio_filters()

        if saved_entry:
            saved_aid = saved_entry.get("audio_track")
            saved_sid = saved_entry.get("subtitle_track")
            if saved_aid and not audio_file:
                GLib.timeout_add(300, lambda: self.core.set_audio_track(saved_aid))
            if saved_sid and not sub_file:
                GLib.timeout_add(300, lambda: self.core.set_subtitle_track(saved_sid))

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
        if not self.equalizer.enabled:
            self.core.equalizer_bands = [0.0] * 10
            eq_filter = ""
        else:
            for idx in range(10):
                self.core.equalizer_bands[idx] = self.equalizer.get_band(idx)
            eq_filter = self.equalizer.to_filter_string()
        filter_chain = self.dsp.build_filter_chain(eq_filter)
        self.core.set_property("af", filter_chain)

    def toggle_normalizer(self, active: bool) -> None:
        self.dsp.normalizer_enabled = active
        self.apply_audio_filters()

    def toggle_audio_enhancement(self, enabled: Optional[bool] = None) -> None:
        if enabled is None:
            new_state = not self.dsp.enhancement_enabled
        else:
            new_state = bool(enabled)
        self.dsp.set_enhancement_enabled(new_state)
        self.db.set_setting("audio_enhancement_enabled", "1" if self.dsp.enhancement_enabled else "0")
        self.db.set_setting("audio_enhancement_preset", self.dsp.enhancement_preset)
        self.apply_audio_filters()
        st = "ON" if self.dsp.enhancement_enabled else "OFF"
        self.osd.show_osd(f"Audio Enhancement: {st} ({self.dsp.enhancement_preset})")

    def set_audio_enhancement_preset(self, preset_name: str) -> None:
        if self.dsp.set_enhancement_preset(preset_name):
            self.db.set_setting("audio_enhancement_preset", preset_name)
            self.db.set_setting("audio_enhancement_enabled", "1" if self.dsp.enhancement_enabled else "0")
            self.apply_audio_filters()
            self.osd.show_osd(f"Audio Enhancement Preset: {preset_name}")

    def set_audio_enhancement_gain(self, gain_db: float) -> None:
        self.dsp.set_enhancement_gain(gain_db)
        self.db.set_setting("audio_enhancement_gain", str(self.dsp.enhancement_gain_db))
        self.apply_audio_filters()
        self.osd.show_osd(f"Audio Enhancement Gain: +{self.dsp.enhancement_gain_db:.1f} dB")

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
        entry.set_activates_default(True)
        dialog.set_default_response(Gtk.ResponseType.OK)
        box.add(entry)
        dialog.show_all()
        if dialog.run() == Gtk.ResponseType.OK:
            url = entry.get_text().strip()
            if url:
                self.add_files_to_playlist([url], auto_play=True)
        dialog.destroy()

    def _open_torrent_dialog(self, initial_source: Optional[str] = None) -> None:
        dialog = TorrentStreamDialog(
            parent=self,
            manager=self.torrent_manager,
            on_start_playback=self._on_torrent_stream_started,
            initial_source=initial_source,
        )
        try:
            dialog.run()
        finally:
            if not getattr(dialog, "_is_destroyed", False):
                dialog.destroy()

    def _on_torrent_stream_started(self, stream_url: str, title: str) -> None:
        display_title = f"[Torrent] {title}"
        self.add_files_to_playlist([stream_url], auto_play=True, clear_existing=True)
        if self.playlist and self.current_index >= 0:
            self.playlist[self.current_index]["title"] = display_title
            self.playlist_window.update_playlist(self.playlist)
        self.set_title(f"Jonaki - {display_title}")
        self.osd.show_osd(f"Streaming Torrent: {title}")

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

        # 1. Check for Magnet URI
        if text.startswith("magnet:"):
            self._open_torrent_dialog(initial_source=text)
            return

        # 2. Check for URL (streaming, YouTube, RTSP, HTTP/HTTPS, HLS, DASH, etc.)
        url_schemes = ("http://", "https://", "rtsp://", "rtmp://", "mms://", "ytdl://", "udp://", "tcp://")
        if any(text.startswith(scheme) for scheme in url_schemes):
            self.add_files_to_playlist([text], auto_play=True, clear_existing=True)
            self.osd.show_osd(f"Playing from Clipboard: {text[:45]}...")
            return

        # 3. Check for local file path or file:// URI
        target_path = text
        if target_path.startswith("file://"):
            from urllib.parse import unquote
            target_path = unquote(target_path[7:])

        if os.path.exists(target_path):
            if target_path.lower().endswith(".torrent"):
                self._open_torrent_dialog(initial_source=target_path)
                return
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
            sub_filter.add_pattern(ext.upper())
        dialog.add_filter(sub_filter)

        all_filter = Gtk.FileFilter()
        all_filter.set_name("All Files (*)")
        all_filter.add_pattern("*")
        dialog.add_filter(all_filter)

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
        about.set_comments("Modern high-performance media player for Linux.\nNative in-process libmpv hardware playback with zero external dependencies.")
        about.set_license_type(Gtk.License.GPL_3_0)
        about.set_website("https://github.com/ashik-himel/JonakiPlayer")
        about.run()
        about.destroy()

    def _on_destroy(self, widget):
        if getattr(self, "_ui_timer_id", None):
            try:
                GLib.source_remove(self._ui_timer_id)
            except Exception:
                pass
            self._ui_timer_id = None
        if getattr(self, "_click_timer_id", None):
            try:
                GLib.source_remove(self._click_timer_id)
            except Exception:
                pass
            self._click_timer_id = None
        if hasattr(self, "mpris") and self.mpris:
            self.mpris.stop()
        if hasattr(self, "power_inhibitor") and self.power_inhibitor:
            self.power_inhibitor.uninhibit()
        if hasattr(self, "torrent_manager") and self.torrent_manager:
            self.torrent_manager.stop_session()
        self._save_current_position()
        self._save_audio_settings()
        try:
            self.db.save_playlist(self.playlist)
        except Exception as e:
            print(f"[MediaDB] Failed to save playlist on exit: {e}")
        self.core.stop_engine()
        if Gtk.main_level() > 0:
            Gtk.main_quit()
