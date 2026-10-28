#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Jonaki for Linux - Main Entry Point & Command Line Switch Parser
Full CLI compatibility and PotPlayer-style switches.
Supports /filedlg, /seek=, /sub=, /aud=, /user_agent=, /new, /current, and stdin (-) streaming.
"""

import os
import sys

def ensure_x11_backend() -> None:
    # Guarantee X11 surface embedding under Wayland / XWayland
    if os.environ.get("GDK_BACKEND") != "x11":
        os.environ["GDK_BACKEND"] = "x11"
        try:
            os.execv(sys.executable, [sys.executable] + sys.argv)
        except Exception as e:
            print(f"[Jonaki] Warning: Failed to re-exec with GDK_BACKEND=x11: {e}", file=sys.stderr)


if not os.environ.get("VDPAU_DRIVER"):
    if os.path.exists("/usr/lib/x86_64-linux-gnu/vdpau/libvdpau_radeonsi.so"):
        os.environ["VDPAU_DRIVER"] = "radeonsi"
    elif os.path.exists("/usr/lib/x86_64-linux-gnu/vdpau/libvdpau_va_gl.so"):
        os.environ["VDPAU_DRIVER"] = "va_gl"

import ctypes
try:
    _libc = ctypes.CDLL("libc.so.6")
    _libc.setlocale.argtypes = [ctypes.c_int, ctypes.c_char_p]
    _libc.setlocale.restype = ctypes.c_char_p
    _libc.setlocale(1, b"C")
except Exception:
    pass

import glob
import subprocess
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib

try:
    _libc.setlocale(1, b"C")
except Exception:
    pass

# Add src to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.ipc import IPCClient, IPCServer
from ui.main_window import JonakiMainWindow, PotPlayerMainWindow


def parse_seek_time(seek_str: str) -> float:
    """
    Parses hh:mm:ss.ms or integer seconds string into float seconds.
    Returns 0.0 on malformed input or negative values.
    """
    if not seek_str:
        return 0.0
    seek_str = seek_str.strip().strip('"').strip("'")
    if ":" in seek_str:
        parts = seek_str.split(":")
        try:
            if len(parts) == 3:
                return max(0.0, float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2]))
            elif len(parts) == 2:
                return max(0.0, float(parts[0]) * 60 + float(parts[1]))
        except (ValueError, TypeError):
            return 0.0
    try:
        return max(0.0, float(seek_str))
    except (ValueError, TypeError):
        return 0.0


def parse_arguments(argv: list) -> dict:
    options = {
        "contents": [],
        "filedlg": False,
        "urldlg": False,
        "torrentdlg": False,
        "folderdlg": False,
        "simple": False,
        "cap": False,
        "cam": False,
        "dvd": False,
        "cd": None,
        "add": False,
        "insert": False,
        "autoplay": False,
        "same": False,
        "sort": False,
        "randomize": False,
        "new": False,
        "current": False,
        "clipboard": False,
        "seek": 0.0,
        "sub": None,
        "aud": None,
        "user_agent": None,
        "referer": None,
        "headers": None,
        "title": None,
        "volume": None,
        "config": "Default",
        "stdin_stream": False
    }

    for arg in argv[1:]:
        clean = arg.strip()
        lower = clean.lower()

        # Check stdin stream
        if clean == "-":
            options["stdin_stream"] = True
            options["contents"].append("fd://0")
            continue

        # Check URL schemes
        if any(clean.startswith(prefix) for prefix in ("http://", "https://", "rtsp://", "rtmp://", "mms://", "magnet:", "ytdl://", "udp://", "tcp://", "file://")):
            options["contents"].append(clean)
            continue

        # If it exists on filesystem, treat as content (handles absolute paths /home/..., /tmp/..., etc.)
        if os.path.exists(clean):
            options["contents"].append(os.path.abspath(clean))
            continue

        # Switches starting with / or -
        if lower.startswith("/") or lower.startswith("--") or (lower.startswith("-") and lower != "-"):
            sw = lower.lstrip("/").lstrip("-")
            
            if sw in ("help", "h", "?"):
                print("Jonaki for Linux - High-Performance Multimedia Player (Packed libmpv Core)")
                print("Usage: jonaki [options] [files/urls/folders...]\n")
                print("Options:")
                print("  /filedlg             Open file selection dialog at startup")
                print("  /urldlg              Open URL stream dialog at startup")
                print("  /torrentdlg          Open BitTorrent / Magnet streaming dialog at startup")
                print("  /folderdlg           Open folder dialog at startup")
                print("  /clipboard           Open and play URL/path from system clipboard")
                print("  /new                 Force a new player instance")
                print("  /current             Send media to existing running instance (default)")
                print("  /seek=hh:mm:ss.ms    Seek to timestamp on media open")
                print("  /sub=\"file.srt\"      Load external subtitle file")
                print("  /aud=\"file.m4a\"      Load external audio track")
                print("  /volume=0..100       Set initial volume level")
                print("  /config=\"preset\"     Apply configuration profile preset")
                print("  -                    Stream media directly from standard input (stdin)")
                print("  --help, -h, /?       Show this help message\n")
                sys.exit(0)
            elif sw == "filedlg":
                options["filedlg"] = True
            elif sw == "urldlg":
                options["urldlg"] = True
            elif sw == "torrentdlg":
                options["torrentdlg"] = True
            elif sw == "folderdlg":
                options["folderdlg"] = True
            elif sw == "simple":
                options["simple"] = True
            elif sw == "cap":
                options["cap"] = True
            elif sw == "cam":
                options["cam"] = True
            elif sw == "dvd":
                options["dvd"] = True
            elif sw.startswith("cd"):
                options["cd"] = clean.split(":", 1)[1] if ":" in clean else "default"
            elif sw == "add":
                options["add"] = True
            elif sw == "insert":
                options["insert"] = True
            elif sw == "autoplay":
                options["autoplay"] = True
            elif sw == "same":
                options["same"] = True
            elif sw == "sort":
                options["sort"] = True
            elif sw == "randomize":
                options["randomize"] = True
            elif sw in ("new", "new-instance"):
                options["new"] = True
            elif sw in ("current", "current-instance"):
                options["current"] = True
            elif sw == "clipboard":
                options["clipboard"] = True
            elif sw.startswith("seek="):
                options["seek"] = parse_seek_time(clean.split("=", 1)[1])
            elif sw.startswith("sub="):
                options["sub"] = clean.split("=", 1)[1].strip('"').strip("'")
            elif sw.startswith("aud="):
                options["aud"] = clean.split("=", 1)[1].strip('"').strip("'")
            elif sw.startswith("user_agent="):
                options["user_agent"] = clean.split("=", 1)[1].strip('"').strip("'")
            elif sw.startswith("referer="):
                options["referer"] = clean.split("=", 1)[1].strip('"').strip("'")
            elif sw.startswith("headers="):
                options["headers"] = clean.split("=", 1)[1].strip('"').strip("'")
            elif sw.startswith("title="):
                options["title"] = clean.split("=", 1)[1].strip('"').strip("'")
            elif sw.startswith("volume="):
                try:
                    raw_vol = float(clean.split("=", 1)[1].strip('"').strip("'"))
                    options["volume"] = max(0.0, min(100.0, raw_vol))
                except ValueError:
                    pass
            elif sw.startswith("config="):
                options["config"] = clean.split("=", 1)[1].strip('"').strip("'")
            elif clean.startswith("/") and ("/" not in clean[1:] or "=" in clean):
                if "." in os.path.basename(clean) and "=" not in clean:
                    matches = glob.glob(clean)
                    if matches:
                        options["contents"].extend(matches)
                    else:
                        options["contents"].append(clean)
                else:
                    print(f"[Jonaki] Warning: Unrecognized switch '{clean}'", file=sys.stderr)
            elif lower.startswith("-"):
                print(f"[Jonaki] Warning: Unrecognized switch '{clean}'", file=sys.stderr)
            else:
                # Absolute path or glob that doesn't exist on disk yet
                matches = glob.glob(clean)
                if matches:
                    options["contents"].extend(matches)
                else:
                    options["contents"].append(clean)
        else:
            # Relative path, glob, or target
            matches = glob.glob(clean)
            if matches:
                options["contents"].extend(matches)
            else:
                options["contents"].append(clean)

    return options


def main():
    ensure_x11_backend()
    Gtk.init_check(None)
    options = parse_arguments(sys.argv)

    # Handle single instance /current unless /new was specified
    if not options["new"]:
        client = IPCClient()
        if client.is_server_running():
            # Delegate command to running player
            payload = {
                "command": "open",
                "items": options["contents"],
                "seek": options["seek"],
                "add": options["add"],
                "sub": options["sub"],
                "aud": options["aud"]
            }
            res = client.send_command(payload)
            if res and res.get("status") == "ok":
                print("[Jonaki] Delegated playback request to existing instance.")
                return

    # Initialize Main Application Window
    win = JonakiMainWindow(config_preset=options["config"])

    if options["volume"] is not None:
        win.core.set_volume(options["volume"])

    # Show Window and Realize GTK surface first
    win.show_all()

    if options["contents"]:
        win.add_files_to_playlist(
            options["contents"],
            auto_play=True,
            seek_pts=options["seek"],
            sub_file=options["sub"],
            audio_file=options["aud"]
        )
    else:
        if options["sub"]:
            win.core.load_subtitle(options["sub"])
        if options["aud"]:
            win.core.load_audio_track(options["aud"])

    # Launch IPC Server for receiving secondary instance requests
    def _ipc_handler(msg: dict) -> dict:
        cmd = msg.get("command")
        if cmd == "open":
            items = msg.get("items", [])
            add_mode = msg.get("add", False)
            seek_val = msg.get("seek", 0.0)
            sub_val = msg.get("sub")
            aud_val = msg.get("aud")
            if items:
                # not add_mode means clear existing and play immediately
                GLib.idle_add(win.add_files_to_playlist, items, True, not add_mode, seek_val, sub_val, aud_val)
            else:
                if sub_val:
                    GLib.idle_add(win.core.load_subtitle, sub_val)
                if aud_val:
                    GLib.idle_add(win.core.load_audio_track, aud_val)
                if seek_val > 0:
                    GLib.idle_add(win.core.seek_absolute, seek_val)
            return {"status": "ok"}
        return {"status": "unrecognized_command"}

    server = IPCServer(_ipc_handler)
    server.start()

    if options["filedlg"]:
        win.handle_command("CMD_OPEN_FILE")
    elif options["folderdlg"]:
        win.handle_command("CMD_OPEN_FOLDER")
    elif options["urldlg"]:
        win.handle_command("CMD_OPEN_URL")
    elif options.get("torrentdlg"):
        win.handle_command("CMD_OPEN_TORRENT")
    elif options.get("clipboard"):
        win.handle_command("CMD_OPEN_CLIPBOARD")

    try:
        Gtk.main()
    finally:
        server.stop()


if __name__ == "__main__":
    main()
