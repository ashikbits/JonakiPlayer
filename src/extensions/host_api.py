"""
Jonaki for Linux - Extension API Bridge
Provides Host* APIs compatible with extension specifications.
Executes AngelScript and Python media/subtitle extensions.
"""

import os
import sys
import time
import urllib.request
import urllib.parse
from typing import Dict, Any, Optional, List


class JonakiHostAPI:
    def __init__(self, app_version: str = "1.0.0"):
        self.app_version = app_version
        self.config_dir = os.path.expanduser("~/.config/jonaki")
        self.extensions_dir = os.path.join(self.config_dir, "extensions")
        os.makedirs(self.extensions_dir, exist_ok=True)

    # --- Environmental APIs ---

    def HostGetAPIVersion(self) -> int:
        return 1

    def HostGetVersion(self) -> str:
        return self.app_version

    def HostCheckVersion(self, major: int, minor: int, build: int) -> bool:
        import re
        parts = [int(p) for p in re.findall(r"\d+", self.app_version)]
        curr = (parts[0] if len(parts) > 0 else 0,
                parts[1] if len(parts) > 1 else 0,
                parts[2] if len(parts) > 2 else 0)
        return curr >= (major, minor, build)

    def HostIsWin64(self) -> bool:
        # Returns True only if running on 64-bit Windows
        return sys.platform.startswith("win") and sys.maxsize > 2**32

    def HostSleep(self, ms: int) -> None:
        try:
            from gi.repository import Gtk
            if Gtk.main_level() > 0:
                end_time = time.monotonic() + (ms / 1000.0)
                while time.monotonic() < end_time:
                    while Gtk.events_pending():
                        Gtk.main_iteration_do(False)
                    time.sleep(0.01)
                return
        except Exception:
            pass
        time.sleep(ms / 1000.0)

    def HostGetTickCount(self) -> int:
        return int(time.monotonic() * 1000)

    def HostPrintUTF8(self, log_msg: str) -> None:
        print(f"[Jonaki Host] {log_msg}")

    # --- Filesystem APIs ---

    def HostGetScriptFolder(self) -> str:
        return self.extensions_dir

    def HostGetExtensionFolder(self) -> str:
        return self.extensions_dir

    def HostGetTempFolder(self) -> str:
        return "/tmp"

    def HostGetConfigFolder(self) -> str:
        return self.config_dir

    def HostFileExist(self, file_path: str) -> bool:
        return os.path.isfile(file_path)

    def HostFolderExist(self, folder_path: str) -> bool:
        return os.path.isdir(folder_path)

    # --- Network APIs ---

    def HostUrlGetString(self, url: str, user_agent: str = "Jonaki", referer: str = "", headers_str: str = "") -> str:
        req = urllib.request.Request(url)
        if user_agent:
            req.add_header("User-Agent", user_agent)
        if referer:
            req.add_header("Referer", referer)
        if headers_str:
            for line in headers_str.split("\n"):
                if ":" in line:
                    k, v = line.split(":", 1)
                    req.add_header(k.strip(), v.strip())
        try:
            with urllib.request.urlopen(req, timeout=5.0) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except Exception as e:
            print(f"[HostAPI] HostUrlGetString failed: {e}")
            return ""

    def HostUrlPostData(self, url: str, post_data: str, user_agent: str = "Jonaki", referer: str = "", headers_str: str = "") -> str:
        data = post_data.encode("utf-8")
        req = urllib.request.Request(url, data=data, method="POST")
        if user_agent:
            req.add_header("User-Agent", user_agent)
        if referer:
            req.add_header("Referer", referer)
        if headers_str:
            for line in headers_str.split("\n"):
                if ":" in line:
                    k, v = line.split(":", 1)
                    req.add_header(k.strip(), v.strip())
        try:
            with urllib.request.urlopen(req, timeout=5.0) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except Exception as e:
            print(f"[HostAPI] HostUrlPostData failed: {e}")
            return ""


# Backward compatibility alias
PotPlayerHostAPI = JonakiHostAPI
