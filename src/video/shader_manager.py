"""
Jonaki for Linux - Video Shader & Color Processing Manager
Loads converted GLSL pixel shaders and manages hardware color controls (ProcAmp).
"""

import os
from typing import List, Dict, Optional


class VideoShaderManager:
    def __init__(self, shaders_dir: Optional[str] = None):
        if shaders_dir is None:
            # Look in assets/shaders relative to project root
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            shaders_dir = os.path.join(base_dir, "assets", "shaders")
        self.shaders_dir = shaders_dir
        self.active_shaders: List[str] = []

        # Color adjustments (ProcAmp): default 0 (range -100 to +100)
        self.brightness: int = 0
        self.contrast: int = 0
        self.saturation: int = 0
        self.hue: int = 0
        self.gamma: int = 0

        # Deinterlacing
        self.deinterlace_mode: str = "no"  # "no", "yes", "auto"

    def get_available_shaders(self) -> List[str]:
        if not os.path.isdir(self.shaders_dir):
            return []
        files = os.listdir(self.shaders_dir)
        return sorted([f for f in files if f.endswith(".hook") or f.endswith(".glsl")])

    def enable_shader(self, shader_filename: str) -> bool:
        if not shader_filename or not shader_filename.strip():
            return False
        safe_name = os.path.basename(shader_filename)
        if not safe_name:
            return False
        full_path = os.path.join(self.shaders_dir, safe_name)
        if os.path.isfile(full_path) and full_path not in self.active_shaders:
            self.active_shaders.append(full_path)
            return True
        return False

    def disable_shader(self, shader_filename: str) -> bool:
        if not shader_filename or not shader_filename.strip():
            return False
        safe_name = os.path.basename(shader_filename)
        if not safe_name:
            return False
        full_path = os.path.join(self.shaders_dir, safe_name)
        if full_path in self.active_shaders:
            self.active_shaders.remove(full_path)
            return True
        return False

    def toggle_shader(self, shader_filename: str) -> bool:
        if not shader_filename or not shader_filename.strip():
            return False
        safe_name = os.path.basename(shader_filename)
        if not safe_name:
            return False
        full_path = os.path.join(self.shaders_dir, safe_name)
        if full_path in self.active_shaders:
            self.active_shaders.remove(full_path)
            return False
        else:
            if os.path.isfile(full_path):
                self.active_shaders.append(full_path)
                return True
            return False

    def clear_shaders(self) -> None:
        self.active_shaders.clear()

    def get_glsl_shaders_string(self) -> str:
        """
        Returns colon-separated or list string suitable for mpv glsl-shaders property.
        """
        return ":".join(self.active_shaders)

    def set_color(self, name: str, val: int) -> int:
        clamped = max(-100, min(100, int(val)))
        if name == "brightness":
            self.brightness = clamped
        elif name == "contrast":
            self.contrast = clamped
        elif name == "saturation":
            self.saturation = clamped
        elif name == "hue":
            self.hue = clamped
        elif name == "gamma":
            self.gamma = clamped
        return clamped

    def reset_colors(self) -> None:
        self.brightness = 0
        self.contrast = 0
        self.saturation = 0
        self.hue = 0
        self.gamma = 0
