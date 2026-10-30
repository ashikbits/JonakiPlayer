# Linux Development & Packaging Guide: Jonaki for Linux

This document provides complete instructions for developers building, testing, extending, and packaging **Jonaki for Linux**.

---

## 1. System Prerequisites & Dependencies

### 1.1 Debian 13 (Trixie) / Ubuntu 24.04+
```bash
sudo apt-get update && sudo apt-get install -y \
    build-essential \
    python3 \
    python3-gi \
    python3-cairo \
    libgstreamer1.0-0 \
    gstreamer1.0-plugins-base \
    gstreamer1.0-plugins-good \
    gstreamer1.0-plugins-bad \
    gstreamer1.0-plugins-ugly \
    gstreamer1.0-libav \
    gstreamer1.0-gtk3 \
    ffmpeg \
    pipewire \
    yt-dlp
```

### 1.2 Fedora 40+
```bash
sudo dnf install -y \
    python3 python3-gobject python3-cairo \
    gstreamer1 gstreamer1-plugins-base gstreamer1-plugins-good \
    gstreamer1-plugins-bad-free gstreamer1-plugins-ugly-free \
    gstreamer1-plugin-libav gstreamer1-plugin-gtk4 \
    ffmpeg pipewire yt-dlp
```

---

## 2. Launching and Running in Development

### 2.1 Running the Player Directly via the Launcher
```bash
# Launch player
./bin/jonaki

# Open a video file with 5-second initial seek
./bin/jonaki /path/to/video.mkv /seek=00:05:00

# Stream video from stdin
yt-dlp -o - -f best "https://www.youtube.com/watch?v=..." | ./bin/jonaki -

# Open video with external subtitle and initial volume
./bin/jonaki video.mp4 /sub="sub.srt" /volume=80
```

### 3.2 Running Conformance Tests
```bash
python3 -m unittest discover -s tests -p "test_*.py" -v
```

---

## 4. Packaging for Linux Distributions

### 4.1 AppImage Packaging
Using `appimagetool` to produce a portable single-binary executable containing all dependencies (Python runtime, GTK4 libraries, FFmpeg, and MPV):
```bash
python3 scripts/build_appimage.py --output Jonaki-x86_64.AppImage
```

### 4.2 Flatpak Packaging
The `io.github.jonaki_linux.Jonaki.yml` manifest packages Jonaki with Wayland, X11, PipeWire, and GPU device permissions:
```yaml
app-id: io.github.jonaki_linux.Jonaki
runtime: org.freedesktop.Platform
runtime-version: '24.08'
sdk: org.freedesktop.Sdk
command: jonaki
finish-args:
  - --share=ipc
  - --socket=fallback-x11
  - --socket=wayland
  - --device=dri
  - --socket=pulseaudio
  - --filesystem=host
```

### 4.3 Debian Package (`.deb`)
```bash
dpkg-buildpackage -us -uc -b
```
