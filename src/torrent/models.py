# SPDX-License-Identifier: GPL-3.0-or-later
"""
Data models and constants for the Torrent Streaming subsystem.
"""

from dataclasses import dataclass, field
import os
from typing import List, Optional

VIDEO_EXTENSIONS = {
    ".mp4", ".mkv", ".avi", ".webm", ".mov", ".flv", ".wmv",
    ".ts", ".m4v", ".mpg", ".mpeg", ".vob", ".ogv", ".3gp",
    ".m2ts", ".mts", ".asf", ".f4v"
}

def is_video_file(file_path: str) -> bool:
    """Returns True if the file path has a recognized video container extension."""
    _, ext = os.path.splitext(file_path.lower())
    return ext in VIDEO_EXTENSIONS

@dataclass
class TorrentFileInfo:
    """Information regarding an individual file within a torrent."""
    index: int
    name: str
    path: str
    size: int
    offset: int
    is_video: bool
    priority: int = 4  # Default priority in libtorrent 2.x

    @property
    def formatted_size(self) -> str:
        """Returns a human-readable size string (e.g. 1.45 GB)."""
        bytes_val = float(self.size)
        for unit in ["B", "KB", "MB", "GB", "TB"]:
            if bytes_val < 1024.0 or unit == "TB":
                return f"{bytes_val:.2f} {unit}" if unit != "B" else f"{int(bytes_val)} B"
            bytes_val /= 1024.0
        return f"{self.size} B"

@dataclass
class TorrentStatusInfo:
    """Live status metrics of an active torrent session."""
    name: str = ""
    info_hash: str = ""
    total_size: int = 0
    progress: float = 0.0  # 0.0 to 1.0
    download_rate: int = 0  # Bytes / sec
    upload_rate: int = 0  # Bytes / sec
    num_peers: int = 0
    num_seeds: int = 0
    state: str = "stopped"
    has_metadata: bool = False
    piece_count: int = 0
    pieces_completed: int = 0
    selected_file_index: Optional[int] = None
    files: List[TorrentFileInfo] = field(default_factory=list)
    error_message: Optional[str] = None

    @property
    def formatted_download_rate(self) -> str:
        rate = float(self.download_rate)
        for unit in ["B/s", "KB/s", "MB/s", "GB/s"]:
            if rate < 1024.0 or unit == "GB/s":
                return f"{rate:.1f} {unit}"
            rate /= 1024.0
        return f"{self.download_rate} B/s"

    @property
    def formatted_progress(self) -> str:
        return f"{self.progress * 100:.1f}%"
