"""
Jonaki for Linux - MPRIS2 D-Bus Interface
Implements org.mpris.MediaPlayer2 and org.mpris.MediaPlayer2.Player for seamless desktop integration.
Binds to system media keys (Play/Pause, Next, Prev, Stop), lockscreens, and desktop media widgets.
Uses Gio GDBus native integration with the GLib main loop.
"""

import os
import math
from pathlib import Path
from typing import Any, Optional, Dict
import gi
gi.require_version('Gio', '2.0')
gi.require_version('GLib', '2.0')
from gi.repository import Gio, GLib


MPRIS_INTROSPECTION_XML = """
<node>
  <interface name="org.mpris.MediaPlayer2">
    <method name="Raise"/>
    <method name="Quit"/>
    <property name="CanQuit" type="b" access="read"/>
    <property name="Fullscreen" type="b" access="readwrite"/>
    <property name="CanSetFullscreen" type="b" access="read"/>
    <property name="CanRaise" type="b" access="read"/>
    <property name="HasTrackList" type="b" access="read"/>
    <property name="Identity" type="s" access="read"/>
    <property name="DesktopEntry" type="s" access="read"/>
    <property name="SupportedUriSchemes" type="as" access="read"/>
    <property name="SupportedMimeTypes" type="as" access="read"/>
  </interface>
  <interface name="org.mpris.MediaPlayer2.Player">
    <method name="Next"/>
    <method name="Previous"/>
    <method name="Pause"/>
    <method name="PlayPause"/>
    <method name="Stop"/>
    <method name="Play"/>
    <method name="Seek">
      <arg direction="in" name="Offset" type="x"/>
    </method>
    <method name="SetPosition">
      <arg direction="in" name="TrackId" type="o"/>
      <arg direction="in" name="Position" type="x"/>
    </method>
    <method name="OpenUri">
      <arg direction="in" name="Uri" type="s"/>
    </method>
    <signal name="Seeked">
      <arg name="Position" type="x"/>
    </signal>
    <property name="PlaybackStatus" type="s" access="read"/>
    <property name="LoopStatus" type="s" access="readwrite"/>
    <property name="Rate" type="d" access="readwrite"/>
    <property name="Metadata" type="a{sv}" access="read"/>
    <property name="Volume" type="d" access="readwrite"/>
    <property name="Position" type="x" access="read"/>
    <property name="MinimumRate" type="d" access="read"/>
    <property name="MaximumRate" type="d" access="read"/>
    <property name="CanControl" type="b" access="read"/>
    <property name="CanPlay" type="b" access="read"/>
    <property name="CanPause" type="b" access="read"/>
    <property name="CanSeek" type="b" access="read"/>
    <property name="CanGoNext" type="b" access="read"/>
    <property name="CanGoPrevious" type="b" access="read"/>
  </interface>
</node>
"""


class MPRIS2Service:
    """
    MPRIS2 Media Player controller providing D-Bus endpoints for desktop environments.
    """
    OBJECT_PATH = "/org/mpris/MediaPlayer2"
    BUS_NAME_PREFIX = "org.mpris.MediaPlayer2.jonaki"

    def __init__(self, main_window: Any):
        self.win = main_window
        self.connection: Optional[Gio.DBusConnection] = None
        self.owner_id: int = 0
        self.reg_id_root: int = 0
        self.reg_id_player: int = 0
        self._node_info = Gio.DBusNodeInfo.new_for_xml(MPRIS_INTROSPECTION_XML)
        self._mpris_iface = self._node_info.lookup_interface("org.mpris.MediaPlayer2")
        self._player_iface = self._node_info.lookup_interface("org.mpris.MediaPlayer2.Player")

    def start(self) -> bool:
        """
        Registers the MPRIS2 service name on the D-Bus session bus.
        """
        bus_name = f"{self.BUS_NAME_PREFIX}.instance_{os.getpid()}"
        try:
            self.owner_id = Gio.bus_own_name(
                Gio.BusType.SESSION,
                bus_name,
                Gio.BusNameOwnerFlags.NONE,
                self._on_bus_acquired,
                self._on_name_acquired,
                self._on_name_lost
            )
            return True
        except Exception as e:
            print(f"[MPRIS2] Failed to initialize D-Bus service: {e}")
            return False

    def stop(self) -> None:
        """
        Unregisters D-Bus name and object.
        """
        if self.connection and self.reg_id_root:
            try:
                self.connection.unregister_object(self.reg_id_root)
            except Exception:
                pass
            self.reg_id_root = 0
        if self.connection and self.reg_id_player:
            try:
                self.connection.unregister_object(self.reg_id_player)
            except Exception:
                pass
            self.reg_id_player = 0
        if self.owner_id:
            try:
                Gio.bus_unown_name(self.owner_id)
            except Exception:
                pass
            self.owner_id = 0

    def _on_bus_acquired(self, connection: Gio.DBusConnection, name: str) -> None:
        self.connection = connection
        try:
            # Register Root Interface
            self.reg_id_root = connection.register_object(
                self.OBJECT_PATH,
                self._mpris_iface,
                self._on_root_method_call,
                self._on_root_get_property,
                self._on_root_set_property
            )
            # Register Player Interface
            self.reg_id_player = connection.register_object(
                self.OBJECT_PATH,
                self._player_iface,
                self._on_player_method_call,
                self._on_player_get_property,
                self._on_player_set_property
            )
        except Exception as e:
            print(f"[MPRIS2] Error registering D-Bus object: {e}")

    def _on_name_acquired(self, connection: Gio.DBusConnection, name: str) -> None:
        pass

    def _on_name_lost(self, connection: Optional[Gio.DBusConnection], name: str) -> None:
        pass

    # --- Root Interface Callbacks ---

    def _on_root_method_call(self, conn, sender, object_path, iface_name, method_name, parameters, invocation):
        if method_name == "Raise":
            self.win.present()
            invocation.return_value(None)
        elif method_name == "Quit":
            self.win.handle_command("CMD_APP_EXIT")
            invocation.return_value(None)
        else:
            invocation.return_error_literal(Gio.dbus_error_quark(), Gio.DBusError.UNKNOWN_METHOD, f"Unknown method {method_name}")

    def _on_root_get_property(self, conn, sender, object_path, iface_name, prop_name):
        if prop_name == "CanQuit":
            return GLib.Variant("b", True)
        elif prop_name == "Fullscreen":
            return GLib.Variant("b", getattr(self.win, "is_fullscreen", False))
        elif prop_name == "CanSetFullscreen":
            return GLib.Variant("b", True)
        elif prop_name == "CanRaise":
            return GLib.Variant("b", True)
        elif prop_name == "HasTrackList":
            return GLib.Variant("b", False)
        elif prop_name == "Identity":
            return GLib.Variant("s", "Jonaki")
        elif prop_name == "DesktopEntry":
            return GLib.Variant("s", "jonaki")
        elif prop_name == "SupportedUriSchemes":
            return GLib.Variant("as", ["file", "http", "https", "rtsp"])
        elif prop_name == "SupportedMimeTypes":
            return GLib.Variant("as", ["video/mp4", "video/x-matroska", "video/webm", "video/avi", "video/quicktime", "audio/mpeg", "audio/flac", "audio/ogg"])
        return None

    def _on_root_set_property(self, conn, sender, object_path, iface_name, prop_name, value):
        if prop_name == "Fullscreen":
            should_fs = value.get_boolean()
            if should_fs != getattr(self.win, "is_fullscreen", False):
                self.win.toggle_fullscreen()
            return True
        return False

    # --- Player Interface Callbacks ---

    def _on_player_method_call(self, conn, sender, object_path, iface_name, method_name, parameters, invocation):
        core = getattr(self.win, "core", None)
        if not core:
            invocation.return_value(None)
            return

        if method_name == "Next":
            self.win.play_next()
            invocation.return_value(None)
        elif method_name == "Previous":
            self.win.play_prev()
            invocation.return_value(None)
        elif method_name == "Pause":
            core.pause()
            invocation.return_value(None)
        elif method_name == "PlayPause":
            self.win.toggle_play_pause()
            invocation.return_value(None)
        elif method_name == "Stop":
            core.stop()
            invocation.return_value(None)
        elif method_name == "Play":
            core.play()
            invocation.return_value(None)
        elif method_name == "Seek":
            (offset_us,) = parameters.unpack()
            offset_sec = offset_us / 1000000.0
            core.seek_relative(offset_sec)
            self.notify_seeked(core.position)
            invocation.return_value(None)
        elif method_name == "SetPosition":
            (track_id, position_us) = parameters.unpack()
            if track_id == "/org/mpris/MediaPlayer2/CurrentTrack" and position_us >= 0:
                pos_sec = position_us / 1000000.0
                if not core.duration or pos_sec <= core.duration:
                    core.seek_absolute(pos_sec)
                    self.notify_seeked(core.position)
            invocation.return_value(None)
        elif method_name == "OpenUri":
            (uri,) = parameters.unpack()
            self.win.play_file(uri)
            invocation.return_value(None)
        else:
            invocation.return_error_literal(Gio.dbus_error_quark(), Gio.DBusError.UNKNOWN_METHOD, f"Unknown method {method_name}")

    def _on_player_get_property(self, conn, sender, object_path, iface_name, prop_name):
        core = getattr(self.win, "core", None)
        if prop_name == "PlaybackStatus":
            status = "Stopped"
            if core:
                st = str(getattr(core, "state", "")).lower()
                if "playing" in st:
                    status = "Playing"
                elif "paused" in st:
                    status = "Paused"
            return GLib.Variant("s", status)
        elif prop_name == "LoopStatus":
            loop_status = "None"
            if core:
                loop_file = core.get_property("loop-file")
                loop_playlist = core.get_property("loop-playlist")
                if loop_file == "inf":
                    loop_status = "Track"
                elif loop_playlist == "inf":
                    loop_status = "Playlist"
            return GLib.Variant("s", loop_status)
        elif prop_name == "Rate":
            speed = core.speed if core else 1.0
            return GLib.Variant("d", float(speed))
        elif prop_name == "Metadata":
            return self._build_metadata_variant()
        elif prop_name == "Volume":
            vol = (core.volume / 100.0) if core else 1.0
            return GLib.Variant("d", max(0.0, min(1.0, float(vol))))
        elif prop_name == "Position":
            pos = core.position if core else 0.0
            pos_us = int(pos * 1000000) if (math.isfinite(pos) and pos >= 0) else 0
            return GLib.Variant("x", pos_us)
        elif prop_name == "MinimumRate":
            return GLib.Variant("d", 0.1)
        elif prop_name == "MaximumRate":
            return GLib.Variant("d", 16.0)
        elif prop_name in ("CanControl", "CanPlay", "CanPause", "CanSeek", "CanGoNext", "CanGoPrevious"):
            return GLib.Variant("b", True)
        return None

    def _on_player_set_property(self, conn, sender, object_path, iface_name, prop_name, value):
        core = getattr(self.win, "core", None)
        if not core:
            return False

        if prop_name == "Volume":
            vol_ratio = value.get_double()
            core.set_volume(vol_ratio * 100.0)
            return True
        elif prop_name == "Rate":
            core.set_speed(value.get_double())
            return True
        elif prop_name == "LoopStatus":
            status_str = value.get_string()
            if status_str == "Track":
                core.set_property("loop-file", "inf")
                core.set_property("loop-playlist", "no")
            elif status_str == "Playlist":
                core.set_property("loop-file", "no")
                core.set_property("loop-playlist", "inf")
            else:
                core.set_property("loop-file", "no")
                core.set_property("loop-playlist", "no")
            return True
        return False

    def _build_metadata_variant(self) -> GLib.Variant:
        core = getattr(self.win, "core", None)
        meta: Dict[str, GLib.Variant] = {}
        
        if core and core.current_file:
            meta["mpris:trackid"] = GLib.Variant("o", "/org/mpris/MediaPlayer2/CurrentTrack")
            dur = core.duration
            dur_us = int(dur * 1000000) if (math.isfinite(dur) and dur > 0) else 0
            meta["mpris:length"] = GLib.Variant("x", max(0, dur_us))
            title = core.current_title or os.path.basename(core.current_file)
            meta["xesam:title"] = GLib.Variant("s", title)
            if "://" in core.current_file:
                url = core.current_file
            else:
                url = Path(os.path.abspath(core.current_file)).as_uri()
            meta["xesam:url"] = GLib.Variant("s", url)
        else:
            meta["mpris:trackid"] = GLib.Variant("o", "/org/mpris/MediaPlayer2/TrackList/NoTrack")

        return GLib.Variant("a{sv}", meta)

    def notify_seeked(self, position_sec: float) -> None:
        """
        Emits Seeked signal when position changes via Seek or SetPosition.
        """
        if not self.connection:
            return
        pos_us = int(position_sec * 1000000) if (math.isfinite(position_sec) and position_sec >= 0) else 0
        try:
            self.connection.emit_signal(
                None,
                self.OBJECT_PATH,
                "org.mpris.MediaPlayer2.Player",
                "Seeked",
                GLib.Variant("(x)", (pos_us,))
            )
        except Exception:
            pass

    def notify_playback_changed(self) -> None:
        """
        Emits PropertiesChanged signal to desktop notifications/widgets when state changes.
        """
        if not self.connection:
            return

        core = getattr(self.win, "core", None)
        status = "Stopped"
        if core:
            st = str(getattr(core, "state", "")).lower()
            if "playing" in st:
                status = "Playing"
            elif "paused" in st:
                status = "Paused"

        changed = {
            "PlaybackStatus": GLib.Variant("s", status),
            "Metadata": self._build_metadata_variant()
        }
        try:
            self.connection.emit_signal(
                None,
                self.OBJECT_PATH,
                "org.freedesktop.DBus.Properties",
                "PropertiesChanged",
                GLib.Variant("(sa{sv}as)", (
                    "org.mpris.MediaPlayer2.Player",
                    changed,
                    []
                ))
            )
        except Exception:
            pass
