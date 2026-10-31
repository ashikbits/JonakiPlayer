"""
Jonaki for Linux - Subtitle Coordinator & Multi-Track Manager
Manages primary, secondary, and tertiary subtitle tracks, styles, persistence, and PTS synchronization.
"""

import os
import json
from typing import List, Dict, Optional, Any


class SubtitleTrack:
    def __init__(self, track_id: int, title: str, lang: str = "und", external: bool = False, file_path: Optional[str] = None):
        self.track_id = track_id
        self.title = title
        self.lang = lang
        self.external = external
        self.file_path = file_path


class SubtitleStyle:
    """
    Encapsulates all configurable visual style attributes of subtitles in Jonaki / PotPlayer style.
    """
    def __init__(self,
                 font_family: str = "sans-serif",
                 font_size: int = 48,
                 bold: bool = False,
                 italic: bool = False,
                 primary_color: str = "#FFFFFF",
                 outline_color: str = "#000000",
                 outline_width: float = 3.0,
                 shadow_color: str = "#000000",
                 shadow_offset: float = 0.0,
                 back_color: str = "#000000",
                 back_alpha: float = 0.0,
                 pos: int = 100,
                 margin_y: int = 34,
                 margin_x: int = 19,
                 align_x: str = "center",
                 align_y: str = "bottom",
                 spacing: float = 0.0,
                 ass_override: str = "scale"):
        self.font_family = font_family
        self.font_size = font_size
        self.bold = bold
        self.italic = italic
        self.primary_color = primary_color
        self.outline_color = outline_color
        self.outline_width = outline_width
        self.shadow_color = shadow_color
        self.shadow_offset = shadow_offset
        self.back_color = back_color
        self.back_alpha = back_alpha  # 0.0 = transparent, 1.0 = solid
        self.pos = pos
        self.margin_y = margin_y
        self.margin_x = margin_x
        self.align_x = align_x
        self.align_y = align_y
        self.spacing = spacing
        self.ass_override = ass_override

    def to_dict(self) -> Dict[str, Any]:
        return {
            "font_family": self.font_family,
            "font_size": self.font_size,
            "bold": self.bold,
            "italic": self.italic,
            "primary_color": self.primary_color,
            "outline_color": self.outline_color,
            "outline_width": self.outline_width,
            "shadow_color": self.shadow_color,
            "shadow_offset": self.shadow_offset,
            "back_color": self.back_color,
            "back_alpha": self.back_alpha,
            "pos": self.pos,
            "margin_y": self.margin_y,
            "margin_x": self.margin_x,
            "align_x": self.align_x,
            "align_y": self.align_y,
            "spacing": self.spacing,
            "ass_override": self.ass_override
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SubtitleStyle":
        style = cls()
        if not isinstance(data, dict):
            return style
        for k, v in data.items():
            if hasattr(style, k):
                # Ensure correct types
                target_type = type(getattr(style, k))
                try:
                    setattr(style, k, target_type(v))
                except Exception:
                    setattr(style, k, v)
        return style


class SubtitleManager:
    DEFAULT_CONFIG_PATH = os.path.expanduser("~/.config/jonaki/subtitle_style.json")

    def __init__(self, config_file: Optional[str] = None):
        self.visible: bool = True
        self.primary_track_id: Optional[int] = 1
        self.secondary_track_id: Optional[int] = None
        self.sync_offset_sec: float = 0.0  # Timing offset in seconds

        self.config_file = config_file or self.DEFAULT_CONFIG_PATH
        self.style = SubtitleStyle()
        self.load_style_config()

        # Translation
        self.translation_enabled: bool = False
        self.target_language: str = "en"
        self.tracks: List[SubtitleTrack] = []

    # Backward-compatibility property accessors
    @property
    def font_family(self) -> str:
        return self.style.font_family

    @font_family.setter
    def font_family(self, val: str) -> None:
        self.style.font_family = str(val)

    @property
    def font_size(self) -> int:
        return self.style.font_size

    @font_size.setter
    def font_size(self, val: int) -> None:
        self.style.font_size = int(val)

    @property
    def primary_color(self) -> str:
        return self.style.primary_color

    @primary_color.setter
    def primary_color(self, val: str) -> None:
        self.style.primary_color = str(val)

    @property
    def outline_color(self) -> str:
        return self.style.outline_color

    @outline_color.setter
    def outline_color(self, val: str) -> None:
        self.style.outline_color = str(val)

    @property
    def outline_width(self) -> float:
        return self.style.outline_width

    @outline_width.setter
    def outline_width(self, val: float) -> None:
        self.style.outline_width = float(val)

    @property
    def bottom_margin_percent(self) -> int:
        return self.style.margin_y

    @bottom_margin_percent.setter
    def bottom_margin_percent(self, val: int) -> None:
        self.style.margin_y = int(val)

    @property
    def top_margin_percent(self) -> int:
        return self.style.margin_y

    @top_margin_percent.setter
    def top_margin_percent(self, val: int) -> None:
        self.style.margin_y = int(val)

    def load_style_config(self) -> bool:
        """Loads saved subtitle styles from JSON file."""
        if not self.config_file or not os.path.exists(self.config_file):
            return False
        try:
            with open(self.config_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                self.style = SubtitleStyle.from_dict(data)
                return True
        except Exception:
            pass
        return False

    def save_style_config(self) -> bool:
        """Saves current subtitle style settings to JSON configuration."""
        if not self.config_file:
            return False
        try:
            os.makedirs(os.path.dirname(os.path.abspath(self.config_file)), exist_ok=True)
            with open(self.config_file, "w", encoding="utf-8") as f:
                json.dump(self.style.to_dict(), f, indent=2)
            return True
        except Exception:
            return False

    def reset_style_to_default(self) -> None:
        """Resets style settings to factory default."""
        self.style = SubtitleStyle()
        self.save_style_config()

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
        self.style.font_size = max(12, min(96, self.style.font_size + delta))
        return self.style.font_size

    def decrease_font_size(self, delta: int = 2) -> int:
        self.style.font_size = max(12, min(96, self.style.font_size - delta))
        return self.style.font_size

    def toggle_visibility(self) -> bool:
        self.visible = not self.visible
        return self.visible
