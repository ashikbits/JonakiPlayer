"""
Jonaki for Linux - Context Menu System
Builds the complete right-click popup menu with full playback control.
Includes dynamic audio/subtitle stream selection, dual subtitles, aspect ratios, and video orientation.
"""

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk
from typing import Callable, Any, Optional


class PotContextMenu:
    """
    Right-click menu builder for Jonaki with dynamic stream and format binding.
    """
    def __init__(self, action_dispatcher: Callable[[str, Any], None]):
        self.dispatch = action_dispatcher
        self.menu: Gtk.Menu = Gtk.Menu()

        # Dynamic submenus
        self.audio_streams_menu = Gtk.Menu()
        self.sub_streams_menu = Gtk.Menu()
        self.sub_sec_streams_menu = Gtk.Menu()
        self.aspect_menu = Gtk.Menu()
        self.orientation_menu = Gtk.Menu()
        self.bookmarks_menu = Gtk.Menu()

        self._build_menu()

    def _build_menu(self) -> None:
        # 1. Open Submenu
        open_item = Gtk.MenuItem(label="Open")
        open_menu = Gtk.Menu()
        self._add_action(open_menu, "Open File(s)... \tCtrl+O", "CMD_OPEN_FILE")
        self._add_action(open_menu, "Open Clipboard / Stream \tCtrl+V", "CMD_OPEN_CLIPBOARD")
        self._add_action(open_menu, "Open URL... \tCtrl+U", "CMD_OPEN_URL")
        self._add_action(open_menu, "Open Folder... \tF2", "CMD_OPEN_FOLDER")
        self._add_separator(open_menu)
        self._add_action(open_menu, "Open Screen Capture", "CMD_OPEN_SCREEN_CAPTURE")
        self._add_action(open_menu, "Open Webcam / Device \tCtrl+J", "CMD_OPEN_WEBCAM")
        open_item.set_submenu(open_menu)
        self.menu.append(open_item)

        self._add_separator(self.menu)

        # 2. Playback Controls & Bookmarks
        playback_item = Gtk.MenuItem(label="Playback")
        playback_menu = Gtk.Menu()
        self._add_action(playback_menu, "Play / Pause \tSpace", "CMD_MEDIA_PLAY_PAUSE")
        self._add_action(playback_menu, "Stop \tF4", "CMD_MEDIA_CLOSE")
        self._add_separator(playback_menu)
        self._add_action(playback_menu, "Seek -5 sec \tLeft", "ID_PLAYBACK_5SEC_BACK")
        self._add_action(playback_menu, "Seek +5 sec \tRight", "ID_PLAYBACK_5SEC_FORW")
        self._add_action(playback_menu, "Next Frame \t. / D", "CMD_FRAME_STEP")
        self._add_action(playback_menu, "Previous Frame \t, / F", "CMD_FRAME_BACK_STEP")
        self._add_separator(playback_menu)
        self._add_action(playback_menu, "Speed: Normal (1.0x) \tZ", "CMD_SPEED_NORMAL")
        self._add_action(playback_menu, "Speed: Slower (-0.1x) \tX", "CMD_SPEED_DOWN")
        self._add_action(playback_menu, "Speed: Faster (+0.1x) \tC", "CMD_SPEED_UP")
        self._add_separator(playback_menu)

        # Bookmarks submenu
        bm_item = Gtk.MenuItem(label="Bookmarks")
        bm_item.set_submenu(self.bookmarks_menu)
        self._add_action(self.bookmarks_menu, "Add Bookmark \tP", "CMD_BOOKMARK_ADD")
        self._add_action(self.bookmarks_menu, "Previous Bookmark \tH", "CMD_BOOKMARK_PREV")
        self._add_action(self.bookmarks_menu, "Next Bookmark \tJ", "CMD_BOOKMARK_NEXT")
        self._add_separator(self.bookmarks_menu)
        self._add_action(self.bookmarks_menu, "Clear Bookmarks for Current File", "CMD_BOOKMARK_CLEAR")
        playback_menu.append(bm_item)

        playback_item.set_submenu(playback_menu)
        self.menu.append(playback_item)

        # Direct Play/Pause & Fullscreen shortcuts in root
        self._add_action(self.menu, "Fullscreen \tEnter", "CMD_FULLSCREEN")
        self._add_action(self.menu, "Stretch Video (Fill Window) \tCtrl+Enter", "CMD_VIDEO_STRETCH")

        self._add_separator(self.menu)

        # 3. Video Submenu
        video_item = Gtk.MenuItem(label="Video")
        video_menu = Gtk.Menu()
        self._add_action(video_menu, "Toggle Hardware Acceleration (HW/SW)", "CMD_TOGGLE_HWDEC")
        self._add_action(video_menu, "Toggle Deinterlacing \tCtrl+F11", "CMD_DEINTERLACE_TOGGLE")
        self._add_action(video_menu, "Toggle Deband Filter \tCtrl+B", "CMD_DEBAND_TOGGLE")
        self._add_action(video_menu, "Toggle HDR Tone-Mapping \tCtrl+H", "CMD_TOGGLE_HDR")
        self._add_action(video_menu, "Reset Video Colors \tQ", "CMD_COLOR_RESET")
        self._add_separator(video_menu)

        # Aspect Ratio Submenu
        aspect_item = Gtk.MenuItem(label="Aspect Ratio")
        aspect_item.set_submenu(self.aspect_menu)
        self._build_aspect_ratio_items()
        video_menu.append(aspect_item)

        # Video Orientation & Flip Submenu
        orient_item = Gtk.MenuItem(label="Orientation & Flip")
        orient_item.set_submenu(self.orientation_menu)
        self._add_action(self.orientation_menu, "Rotate 90° Clockwise \tAlt+K", "CMD_VIDEO_ROTATE")
        self._add_action(self.orientation_menu, "Horizontal Flip (Mirror) \tCtrl+Z", "CMD_VIDEO_HFLIP")
        self._add_action(self.orientation_menu, "Vertical Flip (Invert) \tCtrl+X", "CMD_VIDEO_VFLIP")
        self._add_separator(self.orientation_menu)
        self._add_action(self.orientation_menu, "Reset Orientation", "CMD_VIDEO_RESET_ORIENTATION")
        video_menu.append(orient_item)

        self._add_separator(video_menu)

        # Shaders Submenu
        shaders_item = Gtk.MenuItem(label="Pixel Shaders")
        shaders_menu = Gtk.Menu()
        self._add_action(shaders_menu, "Sharpen (3x3)", "CMD_SHADER_SHARPEN")
        self._add_action(shaders_menu, "Adaptive Sharpen", "CMD_SHADER_ADAPTIVE_SHARPEN")
        self._add_action(shaders_menu, "Denoise", "CMD_SHADER_DENOISE")
        self._add_action(shaders_menu, "Clear Shaders", "CMD_SHADER_CLEAR")
        shaders_item.set_submenu(shaders_menu)
        video_menu.append(shaders_item)

        video_item.set_submenu(video_menu)
        self.menu.append(video_item)

        # 4. Audio Submenu
        audio_item = Gtk.MenuItem(label="Audio")
        audio_menu = Gtk.Menu()

        # Dynamic Audio Stream Selection
        audio_streams_item = Gtk.MenuItem(label="Select Audio Track")
        audio_streams_item.set_submenu(self.audio_streams_menu)
        audio_menu.append(audio_streams_item)

        self._add_action(audio_menu, "Cycle Audio Track \tA", "CMD_CYCLE_AUDIO_TRACK")
        self._add_action(audio_menu, "Toggle Mute \tM", "CMD_AUDIO_MUTE")
        self._add_separator(audio_menu)
        self._add_action(audio_menu, "Audio Enhancement (Loudness) \tShift+E", "CMD_AUDIO_ENHANCE_TOGGLE")
        
        # Audio Enhancement Presets Submenu
        enh_item = Gtk.MenuItem(label="Enhancement Presets")
        enh_menu = Gtk.Menu()
        self._add_action(enh_menu, "Off (Bit-Perfect)", "CMD_AUDIO_ENHANCE_PRESET_Off")
        self._add_action(enh_menu, "Gentle / Low (+3 dB)", "CMD_AUDIO_ENHANCE_PRESET_Gentle_/_Low")
        self._add_action(enh_menu, "Balanced / Default (+5 dB)", "CMD_AUDIO_ENHANCE_PRESET_Balanced_/_Default")
        self._add_action(enh_menu, "Dialogue Focus (+5.5 dB)", "CMD_AUDIO_ENHANCE_PRESET_Dialogue_Focus")
        self._add_action(enh_menu, "Dynamic / High (+7.5 dB)", "CMD_AUDIO_ENHANCE_PRESET_Dynamic_/_High")
        enh_item.set_submenu(enh_menu)
        audio_menu.append(enh_item)

        self._add_separator(audio_menu)
        self._add_action(audio_menu, "Audio Normalizer \tShift+N", "CMD_AUDIO_NORMALIZER_TOGGLE")
        self._add_action(audio_menu, "Volume Boost PreAmp (+1 dB) \tShift+Up", "CMD_AUDIO_BOOST_UP")
        self._add_action(audio_menu, "Volume Boost PreAmp (-1 dB) \tShift+Down", "CMD_AUDIO_BOOST_DOWN")
        self._add_separator(audio_menu)
        self._add_action(audio_menu, "Audio Sync -50ms \tShift+[", "CMD_AUDIO_SYNC_MINUS")
        self._add_action(audio_menu, "Audio Sync +50ms \tShift+]", "CMD_AUDIO_SYNC_PLUS")
        self._add_action(audio_menu, "Audio Sync Reset \tShift+\\", "CMD_AUDIO_SYNC_RESET")
        self._add_separator(audio_menu)
        self._add_action(audio_menu, "Equalizer Dialog... \tF7", "CMD_EQUALIZER_DIALOG")
        audio_item.set_submenu(audio_menu)
        self.menu.append(audio_item)

        # 5. Subtitles Submenu
        sub_item = Gtk.MenuItem(label="Subtitles")
        sub_menu = Gtk.Menu()

        # Dynamic Subtitle Track Selection
        sub_streams_item = Gtk.MenuItem(label="Select Subtitle Track")
        sub_streams_item.set_submenu(self.sub_streams_menu)
        sub_menu.append(sub_streams_item)

        # Dual Subtitle Support: Secondary Subtitle Track
        sub_sec_item = Gtk.MenuItem(label="Secondary Subtitle Track (Dual)")
        sub_sec_item.set_submenu(self.sub_sec_streams_menu)
        sub_menu.append(sub_sec_item)

        self._add_separator(sub_menu)
        self._add_action(sub_menu, "Load Subtitle... \tAlt+O", "CMD_SUB_OPEN")
        self._add_action(sub_menu, "Toggle Subtitle Visibility \tAlt+H", "CMD_SUB_VISIBILITY")
        self._add_action(sub_menu, "Cycle Subtitle Track \tS", "CMD_CYCLE_SUB_TRACK")
        self._add_action(sub_menu, "Cycle Secondary Subtitle \tShift+S", "CMD_CYCLE_SECONDARY_SUB")
        self._add_separator(sub_menu)
        self._add_action(sub_menu, "Move Up \tAlt+Up", "CMD_SUB_POS_UP")
        self._add_action(sub_menu, "Move Down \tAlt+Down", "CMD_SUB_POS_DOWN")
        self._add_action(sub_menu, "Reset Position \tAlt+Home", "CMD_SUB_POS_RESET")
        self._add_action(sub_menu, "Font Size + \tAlt+PgUp", "CMD_SUB_SIZE_UP")
        self._add_action(sub_menu, "Font Size - \tAlt+PgDn", "CMD_SUB_SIZE_DOWN")
        self._add_separator(sub_menu)
        self._add_action(sub_menu, "Sync -0.5s \tAlt+Left", "CMD_SUB_SYNC_MINUS_500")
        self._add_action(sub_menu, "Sync +0.5s \tAlt+Right", "CMD_SUB_SYNC_PLUS_500")
        self._add_action(sub_menu, "Reset Sync \tAlt+/", "CMD_SUB_SYNC_RESET")
        self._add_separator(sub_menu)
        self._add_action(sub_menu, "Real-Time AI Subtitle Translation", "CMD_SUB_TRANSLATE_TOGGLE")
        self._add_action(sub_menu, "Search Subtitles Online... \tCtrl+Alt+S", "CMD_SUB_ONLINE_SEARCH")
        sub_item.set_submenu(sub_menu)
        self.menu.append(sub_item)

        # 6. Capture Submenu
        cap_item = Gtk.MenuItem(label="Capture")
        cap_menu = Gtk.Menu()
        self._add_action(cap_menu, "Save Current Frame \tCtrl+P", "CMD_CAPTURE_FRAME")
        self._add_action(cap_menu, "Save Current Frame As... \tCtrl+E", "CMD_CAPTURE_FRAME_AS")
        self._add_action(cap_menu, "Copy Frame to Clipboard \tCtrl+C", "CMD_CAPTURE_TO_CLIPBOARD")
        self._add_separator(cap_menu)
        self._add_action(cap_menu, "Create Storyboard Sheet", "CMD_CREATE_STORYBOARD")
        self._add_action(cap_menu, "Create Animated GIF \tCtrl+Alt+G", "CMD_CREATE_GIF")
        cap_item.set_submenu(cap_menu)
        self.menu.append(cap_item)

        self._add_separator(self.menu)

        # 7. Panels & Windows
        self._add_action(self.menu, "Control Box... \tF6", "CMD_CONTROL_BOX")
        self._add_action(self.menu, "Playlist... \tF8 / F12", "CMD_PLAYLIST_WINDOW")
        self._add_action(self.menu, "Playback Info (OSD) \tTab", "CMD_OSD_PLAYINFO")
        self._add_action(self.menu, "Media Information... \tCtrl+F1", "CMD_MEDIA_INFO_DIALOG")
        self._add_action(self.menu, "Preferences... \tF5", "CMD_PREFERENCES_DIALOG")

        self._add_separator(self.menu)

        self._add_action(self.menu, "About Jonaki \tF1", "CMD_ABOUT_DIALOG")
        self._add_action(self.menu, "Exit", "CMD_APP_EXIT")

        self.menu.show_all()

    def _build_aspect_ratio_items(self) -> None:
        modes = [
            ("Auto (Keep Aspect Ratio)", "-1"),
            ("Stretch to Window / Screen \tCtrl+Enter", "stretch"),
            ("16:9 Wide Preserved", "16:9"),
            ("4:3 Standard", "4:3"),
            ("2.35:1 CinemaScope", "2.35:1"),
            ("1.85:1 VistaVision", "1.85:1")
        ]
        for label, val in modes:
            item = Gtk.MenuItem(label=label)
            if val == "stretch":
                item.connect("activate", lambda w: self.dispatch("CMD_VIDEO_STRETCH", None))
            else:
                item.connect("activate", lambda w, m=val: self.dispatch("CMD_SET_ASPECT_RATIO", m))
            self.aspect_menu.append(item)

    def refresh_dynamic_menus(self, core: Any) -> None:
        """
        Dynamically populates Audio Streams, Subtitle Tracks, and Secondary Subtitle tracks
        from the live core engine.
        """
        # 1. Audio Tracks
        for child in self.audio_streams_menu.get_children():
            self.audio_streams_menu.remove(child)

        a_tracks = core.get_audio_tracks() if hasattr(core, "get_audio_tracks") else []
        cur_aid = core.get_current_audio_track_id() if hasattr(core, "get_current_audio_track_id") else None

        if a_tracks:
            for t in a_tracks:
                tid = t.get("id")
                lang = t.get("lang") or "und"
                title = t.get("title") or t.get("codec") or "Audio"
                ch = t.get("audio-channels") or 2
                is_selected = t.get("selected") or (str(tid) == str(cur_aid))
                prefix = "✓ " if is_selected else "   "
                label = f"{prefix}Track #{tid}: [{lang}] {title} ({ch}ch)"
                item = Gtk.MenuItem(label=label)
                item.connect("activate", lambda w, target_id=tid: self.dispatch("CMD_SET_AUDIO_TRACK", target_id))
                self.audio_streams_menu.append(item)

            self._add_separator(self.audio_streams_menu)
            dis_prefix = "✓ " if (not cur_aid or cur_aid == "no") else "   "
            dis_item = Gtk.MenuItem(label=f"{dis_prefix}Disable Audio")
            dis_item.connect("activate", lambda w: self.dispatch("CMD_SET_AUDIO_TRACK", "no"))
            self.audio_streams_menu.append(dis_item)
        else:
            none_item = Gtk.MenuItem(label="No Audio Tracks Found")
            none_item.set_sensitive(False)
            self.audio_streams_menu.append(none_item)

        self.audio_streams_menu.show_all()

        # 2. Subtitle Tracks
        for child in self.sub_streams_menu.get_children():
            self.sub_streams_menu.remove(child)

        sub_tracks = core.get_subtitle_tracks() if hasattr(core, "get_subtitle_tracks") else []
        cur_sid = core.get_current_subtitle_track_id() if hasattr(core, "get_current_subtitle_track_id") else None

        if sub_tracks:
            for t in sub_tracks:
                tid = t.get("id")
                lang = t.get("lang") or "und"
                title = t.get("title") or t.get("codec") or "Subtitle"
                is_selected = t.get("selected") or (str(tid) == str(cur_sid))
                prefix = "✓ " if is_selected else "   "
                label = f"{prefix}Track #{tid}: [{lang}] {title}"
                item = Gtk.MenuItem(label=label)
                item.connect("activate", lambda w, target_id=tid: self.dispatch("CMD_SET_SUB_TRACK", target_id))
                self.sub_streams_menu.append(item)

            self._add_separator(self.sub_streams_menu)
            dis_prefix = "✓ " if (not cur_sid or cur_sid == "no") else "   "
            dis_item = Gtk.MenuItem(label=f"{dis_prefix}Disable Subtitles")
            dis_item.connect("activate", lambda w: self.dispatch("CMD_SET_SUB_TRACK", "no"))
            self.sub_streams_menu.append(dis_item)
        else:
            none_item = Gtk.MenuItem(label="No Subtitles Found")
            none_item.set_sensitive(False)
            self.sub_streams_menu.append(none_item)

        self.sub_streams_menu.show_all()

        # 3. Secondary Subtitles (Dual Subtitles)
        for child in self.sub_sec_streams_menu.get_children():
            self.sub_sec_streams_menu.remove(child)

        cur_sec_sid = core.get_current_secondary_subtitle_track_id() if hasattr(core, "get_current_secondary_subtitle_track_id") else None
        dis_sec_prefix = "✓ " if (not cur_sec_sid or cur_sec_sid == "no") else "   "
        dis_sec = Gtk.MenuItem(label=f"{dis_sec_prefix}Disable Secondary Subtitle")
        dis_sec.connect("activate", lambda w: self.dispatch("CMD_SET_SECONDARY_SUB_TRACK", "no"))
        self.sub_sec_streams_menu.append(dis_sec)

        if sub_tracks:
            self._add_separator(self.sub_sec_streams_menu)
            for t in sub_tracks:
                tid = t.get("id")
                lang = t.get("lang") or "und"
                title = t.get("title") or t.get("codec") or "Subtitle"
                is_selected = (str(tid) == str(cur_sec_sid))
                prefix = "✓ " if is_selected else "   "
                label = f"{prefix}Track #{tid}: [{lang}] {title}"
                item = Gtk.MenuItem(label=label)
                item.connect("activate", lambda w, target_id=tid: self.dispatch("CMD_SET_SECONDARY_SUB_TRACK", target_id))
                self.sub_sec_streams_menu.append(item)

        self.sub_sec_streams_menu.show_all()

    def _add_action(self, parent_menu: Gtk.Menu, label: str, cmd_id: str) -> None:
        item = Gtk.MenuItem(label=label)
        item.connect("activate", lambda w: self.dispatch(cmd_id, None))
        parent_menu.append(item)

    def _add_separator(self, parent_menu: Gtk.Menu) -> None:
        sep = Gtk.SeparatorMenuItem()
        parent_menu.append(sep)

    def popup(self, event: Optional[Any] = None, core: Optional[Any] = None) -> None:
        if core is not None:
            self.refresh_dynamic_menus(core)
        if event is not None and hasattr(self.menu, "popup_at_pointer"):
            try:
                self.menu.popup_at_pointer(event)
                return
            except Exception:
                pass
        button = event.button if (event and hasattr(event, "button")) else 0
        time_val = event.time if (event and hasattr(event, "time")) else Gtk.get_current_event_time()
        self.menu.popup(None, None, None, None, button, time_val)
