"""
Jonaki for Linux - Power Management & ScreenSaver Inhibit Service
Prevents the PC from sleeping, dimming, or activating the screensaver during active video playback.
Communicates via standard desktop D-Bus interfaces:
- org.kde.Solid.PowerManagement.PolicyAgent (KDE Plasma screen dimming, idle, and sleep lock)
- org.freedesktop.ScreenSaver (standard freedesktop & XDG screensaver inhibition)
- org.freedesktop.PowerManagement.Inhibit (freedesktop power management)
- org.gnome.SessionManager (GNOME idle & suspend inhibition)
- org.freedesktop.ScreenSaver SimulateUserActivity (periodic heartbeat to reset display dim timers)
"""

import time
from typing import List, Tuple, Optional
import gi
gi.require_version('Gio', '2.0')
from gi.repository import Gio, GLib


class PowerInhibitor:
    """
    Manages D-Bus sleep, display dimming, and screensaver inhibition tokens during active media playback.
    """
    def __init__(self, app_name: str = "Jonaki"):
        self.app_name = app_name
        self.reason = "Video Playback"
        self._bus: Optional[Gio.DBusConnection] = None
        self._active_inhibits: List[Tuple[str, str, str, str, int]] = []
        self._is_inhibited: bool = False
        self._last_heartbeat: float = 0.0

        try:
            self._bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        except Exception:
            self._bus = None

    @property
    def is_inhibited(self) -> bool:
        return self._is_inhibited

    def inhibit(self) -> bool:
        """
        Requests sleep, screen dimming, and screensaver inhibition from active desktop session managers.
        """
        if self._is_inhibited or not self._bus:
            return self._is_inhibited

        services = [
            # 1. KDE Plasma PowerDevil PolicyAgent:
            # Mask 7 = 1 (InterruptSession) | 2 (ChangeScreenSettings / prevent screen dim & off) | 4 (Sleep)
            (
                "org.kde.Solid.PowerManagement.PolicyAgent",
                "/org/kde/Solid/PowerManagement/PolicyAgent",
                "org.kde.Solid.PowerManagement.PolicyAgent",
                "AddInhibition",
                "ReleaseInhibition",
                "(uss)",
                "(u)",
                (7, self.app_name, self.reason)
            ),
            # 2. Standard freedesktop ScreenSaver
            (
                "org.freedesktop.ScreenSaver",
                "/org/freedesktop/ScreenSaver",
                "org.freedesktop.ScreenSaver",
                "Inhibit",
                "UnInhibit",
                "(ss)",
                "(u)",
                (self.app_name, self.reason)
            ),
            # 3. Standard freedesktop PowerManagement
            (
                "org.freedesktop.PowerManagement.Inhibit",
                "/org/freedesktop/PowerManagement/Inhibit",
                "org.freedesktop.PowerManagement.Inhibit",
                "Inhibit",
                "UnInhibit",
                "(ss)",
                "(u)",
                (self.app_name, self.reason)
            ),
            # 4. GNOME SessionManager
            (
                "org.gnome.SessionManager",
                "/org/gnome/SessionManager",
                "org.gnome.SessionManager",
                "Inhibit",
                "Uninhibit",
                "(susu)",
                "(u)",
                (self.app_name, 0, self.reason, 8 | 4)  # 8 = Inhibit idle, 4 = Inhibit suspend
            )
        ]

        acquired_any = False
        for svc_name, obj_path, iface, inh_method, uninh_method, sig_in, sig_out, args in services:
            try:
                res = self._bus.call_sync(
                    svc_name,
                    obj_path,
                    iface,
                    inh_method,
                    GLib.Variant(sig_in, args),
                    GLib.VariantType(sig_out),
                    Gio.DBusCallFlags.NONE,
                    500,
                    None
                )
                cookie = res.unpack()[0]
                self._active_inhibits.append((svc_name, obj_path, iface, uninh_method, cookie))
                acquired_any = True
            except Exception:
                # Service not active on current desktop environment
                pass

        self._is_inhibited = True
        self._last_heartbeat = time.time()
        # Immediately ping activity to ensure display stays at full brightness
        self.heartbeat(force=True)
        return acquired_any

    def uninhibit(self) -> None:
        """
        Releases all active screensaver, display dimming, and power management inhibition tokens.
        """
        if not self._is_inhibited or not self._bus:
            return

        for svc_name, obj_path, iface, uninh_method, cookie in self._active_inhibits:
            try:
                self._bus.call_sync(
                    svc_name,
                    obj_path,
                    iface,
                    uninh_method,
                    GLib.Variant("(u)", (cookie,)),
                    None,
                    Gio.DBusCallFlags.NONE,
                    500,
                    None
                )
            except Exception:
                pass

        self._active_inhibits.clear()
        self._is_inhibited = False

    def heartbeat(self, force: bool = False) -> None:
        """
        Periodically simulates user activity over D-Bus every 30 seconds.
        This resets display idle counters in compositors that enforce separate screen dim timeouts.
        """
        if not self._is_inhibited or not self._bus:
            return

        now = time.time()
        if not force and now - self._last_heartbeat < 30.0:
            return

        self._last_heartbeat = now
        for svc, path, iface in [
            ("org.freedesktop.ScreenSaver", "/org/freedesktop/ScreenSaver", "org.freedesktop.ScreenSaver"),
            ("org.freedesktop.ScreenSaver", "/ScreenSaver", "org.freedesktop.ScreenSaver"),
        ]:
            try:
                self._bus.call_sync(
                    svc,
                    path,
                    iface,
                    "SimulateUserActivity",
                    None,
                    None,
                    Gio.DBusCallFlags.NONE,
                    200,
                    None
                )
            except Exception:
                pass

    def update_state(self, is_playing: bool) -> None:
        """
        Convenience method to synchronize inhibitor state with playback state.
        """
        if is_playing:
            self.inhibit()
        else:
            self.uninhibit()
