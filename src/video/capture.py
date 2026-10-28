"""
Jonaki for Linux - Video Frame Capture, GIF Maker & Storyboard Generator
Replicates Ctrl+P, Ctrl+E, Ctrl+Alt+G (GIF), and Ctrl+Alt+S (Storyboard contact sheet).
"""

import os
import time
import subprocess
from typing import Optional


class MediaCaptureManager:
    def __init__(self, capture_dir: Optional[str] = None):
        if capture_dir is None:
            pictures_dir = os.path.expanduser("~/Pictures")
            capture_dir = os.path.join(pictures_dir, "Jonaki")
        self.capture_dir = capture_dir
        os.makedirs(self.capture_dir, exist_ok=True)

    def generate_capture_filename(self, prefix: str = "Jonaki", ext: str = "png") -> str:
        timestamp = time.strftime("%Y%m%d_%H%M%S") + f"_{int(time.time() * 1000) % 1000:03d}"
        return os.path.join(self.capture_dir, f"{prefix}_{timestamp}.{ext}")

    def create_animated_gif(self, input_file: str, start_sec: float, duration_sec: float = 5.0,
                            output_path: Optional[str] = None, fps: int = 15, scale_width: int = 480) -> Optional[str]:
        """
        Creates a high-quality animated GIF with a two-pass palette generator using FFmpeg.
        """
        if output_path is None:
            output_path = self.generate_capture_filename(prefix="Clip", ext="gif")

        filter_str = f"fps={fps},scale={scale_width}:-1:flags=lanczos,split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse"
        cmd = [
            "ffmpeg", "-y",
            "-ss", str(start_sec),
            "-t", str(duration_sec),
            "-i", input_file,
            "-vf", filter_str,
            output_path
        ]

        try:
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            return output_path
        except Exception as e:
            print(f"[MediaCapture] Animated GIF creation failed: {e}")
            return None

    def create_storyboard(self, input_file: str, duration_sec: float,
                          columns: int = 4, rows: int = 4,
                          output_path: Optional[str] = None) -> Optional[str]:
        """
        Creates a contact sheet / storyboard grid of thumbnails across the video duration.
        """
        if output_path is None:
            output_path = self.generate_capture_filename(prefix="Storyboard", ext="jpg")

        total_frames = columns * rows
        if duration_sec <= 0:
            duration_sec = 60.0

        interval = duration_sec / (total_frames + 1)
        fps_val = 1.0 / interval
        # Select frames evenly spaced across duration
        filter_str = f"fps={fps_val:.6f},scale=320:-1,drawtext=text='%{{pts\\:hms}}':x=10:y=h-th-10:fontcolor=white:box=1:boxcolor=black@0.6,tile={columns}x{rows}"

        cmd = [
            "ffmpeg", "-y",
            "-i", input_file,
            "-vf", filter_str,
            "-vframes", "1",
            output_path
        ]

        try:
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            return output_path
        except Exception as e:
            print(f"[MediaCapture] Storyboard creation failed: {e}")
            return None

    def copy_file_to_clipboard(self, image_path: str) -> bool:
        """
        Copies image to system clipboard via wl-copy (Wayland) or xclip (X11).
        """
        if not os.path.exists(image_path):
            return False

        import mimetypes
        mime_type = mimetypes.guess_type(image_path)[0] or "image/png"

        # Try wl-copy (Wayland)
        try:
            with open(image_path, "rb") as f:
                subprocess.run(["wl-copy", "--type", mime_type], stdin=f, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
                return True
        except (subprocess.SubprocessError, FileNotFoundError):
            pass

        # Try xclip (X11)
        try:
            subprocess.run(["xclip", "-selection", "clipboard", "-t", mime_type, "-i", image_path],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            return True
        except (subprocess.SubprocessError, FileNotFoundError):
            pass

        return False
