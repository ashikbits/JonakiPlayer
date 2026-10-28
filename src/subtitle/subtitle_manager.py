"""
Jonaki for Linux - Subtitle Coordinator & Multi-Track Manager
Manages primary, secondary, and tertiary subtitle tracks, styles, and PTS synchronization.
"""

from typing import List, Dict, Optional, Any


class SubtitleTrack:
    def __init__(self, track_id: int, title: str, lang: str = "und", external: bool = False, file_path: Optional[str] = None):
        self.track_id = track_id
        self.title = title
        self.lang = lang
        self.external = external
        self.file_path = file_path


class SubtitleManager:
    def __init__(self):
        self.visible: bool = True
        self.primary_track_id: Optional[int] = 1
        self.secondary_track_id: Optional[int] = None
        self.sync_offset_sec: float = 0.0  # Timing offset in seconds

        # Styling
        self.font_family: str = "sans-serif"
        self.font_size: int = 48
        self.primary_color: str = "#FFFFFF"
        self.outline_color: str = "#000000"
        self.outline_width: int = 3
        self.bottom_margin_percent: int = 5
        self.top_margin_percent: int = 5

        # Translation
        self.translation_enabled: bool = False
        self.target_language: str = "en"
        self.tracks: List[SubtitleTrack] = []

    def set_tracks(self, tracks: List[SubtitleTrack]) -> None:
        self.tracks = tracks

    def get_track(self, track_id: int) -> Optional[SubtitleTrack]:
        for t in self.tracks:
            if t.track_id == track_id:
                return t
        return None

    def adjust_sync(self, delta_sec: float) -> float:
        self.sync_offset_sec = round(self.sync_offset_sec + delta_sec, 3)
        return self.sync_offset_sec

    def reset_sync(self) -> None:
        self.sync_offset_sec = 0.0

    def increase_font_size(self, delta: int = 2) -> int:
        self.font_size = max(12, min(96, self.font_size + delta))
        return self.font_size

    def decrease_font_size(self, delta: int = 2) -> int:
        self.font_size = max(12, min(96, self.font_size - delta))
        return self.font_size

    def toggle_visibility(self) -> bool:
        self.visible = not self.visible
        return self.visible
