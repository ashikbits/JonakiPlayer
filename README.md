# Jonaki

A native Linux media player engineered for low-latency playback, high-density keyboard workflows, and feature parity with Windows-style advanced media players.

> **Warning: AI SLOP!**

---

## Overview

Jonaki is an open-source multimedia player built natively for Linux desktop environments (GNOME, KDE Plasma, XFCE, wlroots-based compositors, and standalone window managers). 

The project was developed to address a longstanding gap on Linux: the absence of a lightweight, highly responsive, keyboard-driven media player comparable to Daum/Kakao PotPlayer. Rather than running Windows binaries under compatibility layers like Wine or building heavy Electron/web wrappers, Jonaki couples a native GTK 3 interface directly to an in-process `libmpv` playback core via Python C-FFI.

### PotPlayer Compatibility & Heritage

Jonaki implements the established control paradigms and workflow patterns of PotPlayer:
* **Identical keybinding layout:** Default keyboard shortcuts (`Space`, `Enter`, `F1-F12`, `Tab`, `Shift+N`, `Shift+S`, `Ctrl+F1`, `[` / `]`) map directly to their expected operations without requiring muscle-memory retraining.
* **Command-line switch compatibility:** Supports classic PotPlayer CLI invocation syntax (`/seek=`, `/sub=`, `/aud=`, `/filedlg`, `/volume=`, `/new`, `/current`, and stdin `-`).
* **DSF skin parsing:** A dedicated Cairo rasterizer extracts and renders authentic `.dsf` sprite sheets, 9-slice button surfaces, and progress sliders.
* **Dual concurrent subtitles:** Simultaneous primary and secondary subtitle track composition with real-time sync adjustments and translation backend hooks.
* **Audio DSP chain:** 10-band graphic equalizer coupled with automatic volume control (AVC normalizer) and pre-amplification.

*Disclaimer: Jonaki is an independent open-source software project. It is not affiliated with, maintained by, or endorsed by Kakao Corp or Daum Communications.*

---

## Architecture & Technical Design

### 1. In-Process C-FFI Core Engine
Earlier prototypes relying on external `mpv` subprocesses communicated over Unix domain JSON-IPC sockets. In practice, detached subprocesses introduced race conditions during rapid startup, dropped initial seek/subtitle configurations, and struggled with window reparenting under modern display servers.

Jonaki embeds `libmpv` directly in-process using Python `ctypes`:
* Direct C-API invocations eliminate socket serialization latency and IPC handshake overhead.
* Hardware-accelerated decoding pipelines (VA-API, NVDEC, VDPAU, Vulkan) render directly into the allocated X11/XWayland surface (`wid`).
* Enforces numeric C locale (`LC_NUMERIC="C"`) across glibc boundaries to prevent floating-point parsing discrepancies between GTK and `libmpv`.

### 2. Display Server & Surface Embedding
* Operates cleanly across pure Wayland sessions (via XWayland surface abstraction) and native X11 servers.
* Automatically forces `gpu-context=x11egl` to ensure OpenGL contexts bind reliably to the GTK window ID without spawning detached secondary render surfaces.
* Direct GPU OSD path routes high-priority notifications through `mpv`'s text pipeline, avoiding compositing flicker and Cairo buffer stalls over 4K/8K 60fps streams.

### 3. Inter-Process Communication & MPRIS2
* Implements a local Unix domain socket coordinator (`$XDG_RUNTIME_DIR/jonaki_ipc.sock`) supporting single-instance playback delegation (`/current`) and independent execution (`/new`).
* Full MPRIS2 (`org.mpris.MediaPlayer2.jonaki`) D-Bus registration provides immediate interoperability with system media keys, lockscreen widgets, GNOME Shell, KDE Plasma, and `playerctl`.

---

## Dependencies & Prerequisites

### System Packages

Ensure the following system libraries and development runtimes are present:

#### Debian / Ubuntu / Mint
```bash
sudo apt update
sudo apt install -y \
    python3 \
    python3-gi \
    python3-gi-cairo \
    gir1.2-gtk-3.0 \
    libmpv2 \
    ffmpeg \
    libplacebo-dev
```

#### Fedora / RHEL
```bash
sudo dnf install -y \
    python3 \
    python3-gobject \
    gtk3 \
    mpv-libs \
    ffmpeg
```

#### Arch Linux
```bash
sudo pacman -S --needed \
    python \
    python-gobject \
    gtk3 \
    mpv \
    ffmpeg
```

### Optional Utilities
* `yt-dlp`: Enables playback of arbitrary streaming URLs (YouTube, Vimeo, Twitch, HLS/DASH).
* `wl-clipboard` (Wayland) / `xclip` (X11): Enables URL and file path ingestion directly from the system clipboard (`/clipboard` or `Ctrl+U`).

---

## Installation

### Automated User Installation (Recommended)

Run the included installation script to link the launcher binaries and register desktop entries, MIME types, and high-resolution icons into `~/.local/`:

```bash
git clone https://github.com/ashik-himel/JonakiPlayer.git # or your target clone URL
cd PotPlayer
chmod +x install.sh
./install.sh
```

The script performs the following tasks:
1. Links the launcher to `~/.local/bin/jonaki` and creates a `potplayer` compatibility symlink.
2. Installs `jonaki.desktop` into `~/.local/share/applications/` and associates video/audio MIME types.
3. Deploys the application icon into `~/.local/share/icons/hicolor/256x256/apps/`.
4. Triggers `update-desktop-database` and `gtk-update-icon-cache`.

### Manual Installation

If you prefer to configure your environment manually:

```bash
# 1. Symlink launcher to a directory in your PATH
mkdir -p ~/.local/bin
ln -sf "$(pwd)/bin/jonaki" ~/.local/bin/jonaki

# 2. Deploy desktop entry
mkdir -p ~/.local/share/applications
sed -e "s|Exec=jonaki|Exec=$HOME/.local/bin/jonaki|g" \
    -e "s|Icon=.*|Icon=$(pwd)/assets/logos/jonaki.png|g" \
    jonaki.desktop > ~/.local/share/applications/jonaki.desktop
chmod +x ~/.local/share/applications/jonaki.desktop

# 3. Refresh desktop metadata
update-desktop-database ~/.local/share/applications/
```

### Uninstallation

To remove user-level desktop entries, icons, and binary symlinks:

```bash
./uninstall.sh
```

---

## Usage

### Command-Line Execution

```bash
# Launch the main application
jonaki

# Open media file and seek to timestamp
jonaki /path/to/video.mkv /seek=00:15:30

# Specify external subtitles and audio tracks
jonaki movie.mp4 /sub="commentary.srt" /aud="alternate.m4a" /volume=75

# Open file dialog at launch
jonaki /filedlg

# Force a standalone secondary process instead of delegating to existing instance
jonaki /new video.mp4

# Pipe a media stream from standard input
yt-dlp -o - -f best "https://www.youtube.com/watch?v=..." | jonaki -
```

### CLI Parameters Reference

| Parameter | Description |
| :--- | :--- |
| `[file / url / folder]` | Path or URL to enqueue and play immediately |
| `/seek=hh:mm:ss.ms` | Jump to specified timestamp upon opening |
| `/sub="path.srt"` | Load external subtitle file |
| `/aud="path.m4a"` | Load external audio stream |
| `/volume=0..100` | Set initial volume output |
| `/filedlg` | Open file chooser dialog on startup |
| `/urldlg` | Open network stream entry dialog on startup |
| `/clipboard` | Ingest and play media URL or local path from clipboard |
| `/new` | Force a new application process instance |
| `/current` | Delegate playback to running primary instance (default) |
| `-` | Read media stream from standard input (`stdin`) |
| `--help`, `-h`, `/?` | Display command-line parameter help |

---

## Keybindings Reference

| Keybinding | Action |
| :--- | :--- |
| `Space` | Toggle Playback (Play / Pause) |
| `Enter` | Toggle Fullscreen |
| `Ctrl+Enter` | Toggle Stretch-to-Window / Keep Aspect Ratio |
| `Left` / `Right` | Seek backward / forward 5 seconds |
| `Ctrl+Left` / `Ctrl+Right` | Seek backward / forward 30 seconds |
| `Shift+Left` / `Shift+Right` | Seek backward / forward 60 seconds |
| `Up` / `Down` | Volume increment / decrement (+/- 2%) |
| `M` | Toggle Audio Mute |
| `Shift+N` | Toggle Auto Volume Normalizer (AVC) |
| `Shift+S` | Cycle Secondary Subtitle Track (Dual Subtitles) |
| `[` / `]` | Subtitle Sync adjust (-0.5s / +0.5s) |
| `Shift+[` / `Shift+]` | Audio Sync adjust (-0.05s / +0.05s) |
| `Tab` | Toggle Technical Information Overlay (In-GPU HUD) |
| `Ctrl+F1` | Open Media & Stream Properties Report |
| `F6` | Open Quick Control Box (Equalizer, Video ProcAmp, Subtitles) |
| `F7` | Open 10-Band Graphic Equalizer Window |
| `F8` / `F12` | Toggle Playlist Window |
| `Ctrl+Alt+S` | Search Subtitles Online |
| `Ctrl+E` | Export Current Video Frame (Snapshot) |
| `F1` | Open About Dialog |

---

## Verification & Testing

Jonaki includes an automated unit testing suite validating CLI switch parsing, C-FFI initialization, audio equalizer mathematics, persistence schemas, IPC roundtrips, and MPRIS2 interfaces.

Execute the test suite using Python's standard test runner:

```bash
python3 -m unittest discover tests
```

---

## Project Structure

```
.
├── bin/
│   ├── jonaki              # Primary shell launcher
│   └── potplayer           # Compatibility wrapper
├── src/
│   ├── jonaki.py           # Application entry point & CLI switch parser
│   ├── potplayer.py        # Backward-compatibility import wrapper
│   ├── core/
│   │   ├── engine.py       # In-process libmpv C-FFI controller
│   │   ├── ipc.py          # Unix domain socket single-instance protocol
│   │   ├── media_db.py     # SQLite persistence for resume points & bookmarks
│   │   └── mpris.py        # D-Bus MPRIS2 MediaPlayer2 interface
│   ├── ui/
│   │   ├── main_window.py  # Top-level GTK player window & event coordinator
│   │   ├── skin_engine.py  # DSF skin unpacker & Cairo sprite sheet compositor
│   │   ├── context_menu.py # Right-click context menu tree
│   │   ├── control_box.py  # F6 multi-tab adjustment window
│   │   ├── playlist_view.py# F8 / F12 playlist view
│   │   └── osd_overlay.py  # Technical HUD & notification overlay
│   ├── audio/
│   │   ├── equalizer.py    # 10-band graphic equalizer profile models
│   │   └── dsp_chain.py    # Gain staging, AVC normalizer, and limiter
│   ├── video/
│   │   ├── capture.py      # Frame capture, storyboard generator, GIF maker
│   │   └── shader_manager.py # GLSL user shader injection pipeline
│   └── subtitle/
│       ├── subtitle_manager.py # Multi-stream subtitle tracking & sync
│       ├── translator.py   # Translation service client (LLM, DeepL, Google)
│       └── online_search.py# OpenSubtitles hash calculation & retrieval
├── assets/                 # Default skins, logos, and shader hooks
├── docs/                   # Detailed subsystem specifications
├── tests/                  # Automated unit test suite
├── install.sh              # System/user installation script
└── uninstall.sh            # Complete uninstallation script
```

---

## License

Jonaki is licensed under the GNU General Public License v3.0 or later. Refer to the LICENSE file for full terms and conditions.
