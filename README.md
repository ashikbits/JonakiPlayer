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

## Key Features

### 🧲 BitTorrent & Magnet Video Streaming
* **Instant Playback Without Full Downloads:** Stream videos directly from Magnet links (`magnet:?xt=urn:btih:...`) or `.torrent` files with near-instant playback initiation.
* **Local HTTP Loopback Bridge:** Built-in loopback streaming server translates RFC 7233 byte-range seek requests directly into BitTorrent piece requests.
* **Sequential Piece Prioritization & Deadline Scheduling:** Automatically prioritizes file header metadata and video keyframe pieces first, followed by a sliding window buffer ahead of the current playback position for buffer-free scrubbing.
* **Integrated Torrent Dialog (`Ctrl+M` / `/torrentdlg`):** Live swarm dashboard displaying connected peers, seeds, real-time download/upload transfer rates, piece buffer progress bars, and multi-file torrent selection.

### 🔊 Audio Hardening & DSP Enhancement Suite
* **10-Band Graphic Equalizer (`F7`):** Precision frequency response shaping across 31 Hz to 16 kHz with +/- 12 dB range, accompanied by genre presets (Pop, Rock, Classical, Jazz, Club, Vocal, Techno, Full Bass, Soft).
* **Audio Enhancement (Speech Clarity & Loudness) (`Shift+E`):** PotPlayer-style dynamic acoustic expansion with specialized profiles:
  * *Off (Bit-Perfect):* Transparent passthrough.
  * *Gentle / Low (+3 dB):* Subtle dynamic lift.
  * *Balanced / Default (+5 dB):* Standard full-spectrum audio boost.
  * *Dialogue Focus (+5.5 dB):* Center speech band amplification and background compression.
  * *Dynamic / High (+7.5 dB):* High-impact cinema presence.
* **Auto Volume Control (AVC / Normalizer) (`Shift+N`):** Look-ahead limiter and RMS compressor that balances whisper-quiet dialogue and thunderous action sequences without audio clipping.
* **Volume Boost PreAmp (`Shift+Up` / `Shift+Down`):** Clean pre-amplification boost up to +24 dB for low-level media tracks.
* **Precision Audio Delay Sync (`Shift+[` / `Shift+]`):** Millisecond-accurate audio/video synchronization adjustments in 50 ms steps with instant reset (`Shift+\`).

### 💬 Dual Subtitles, AI Translation & Online Search
* **Simultaneous Dual Subtitles:** Render primary subtitles along the bottom and secondary subtitles at the top (or custom positions) concurrently with independent stream selection (`S` / `Shift+S`).
* **Real-Time AI Subtitle Translation (`Alt+T`):** Live translation of foreign-language subtitles powered by cloud APIs (DeepL, Google) or local LLM runtimes (Ollama, LM Studio, vLLM via REST).
* **Online Subtitle Downloader (`Ctrl+Alt+S`):** Integrated OpenSubtitles search with automatic media hash verification and keyword queries.
* **Broad Subtitle Format Support:** Native parsing and rendering of ASS/SSA (with full typography and vector shapes), SRT, VTT, SMI, SUP (Blu-ray PGS), IDX/SUB, and synchronized LRC lyrics.
* **Interactive Adjustments:** Subtitle timing sync offset (`[` / `]`, `Alt+Left` / `Alt+Right`), font size scaling (`Alt+PgUp` / `Alt+PgDn`), vertical positioning (`Alt+Up` / `Alt+Down`), and visibility toggling (`Alt+H`).

### 🎬 Video Engine, Shaders & Hardware Acceleration
* **Hardware Video Acceleration:** Direct GPU-accelerated video decoding via VA-API (Intel/AMD), NVDEC (NVIDIA), VDPAU, and Vulkan Video with direct X11/XWayland surface embedding.
* **HDR to SDR Tone-Mapping:** High-fidelity HDR10 and HLG color-volume conversion to SDR displays via `libplacebo` algorithms (BT.2390, Reinhard, Mobius, Hable).
* **GLSL Pixel Shaders:** Real-time post-processing shaders including 3x3 Sharpen, Adaptive Sharpen, and Denoise filters.
* **Motion-Adaptive Deinterlacing (`Ctrl+F11`):** High-quality broadcast stream deinterlacing (`bwdif`, `yadif`, and hardware deinterlacing).
* **Deband Filter (`Ctrl+B`):** Eliminates 8-bit color banding and posterization artifacts in flat gradients and dark scenes.
* **ProcAmp Color Adjustments:** Instant hardware color controls for Brightness (`W`/`E`), Contrast (`R`/`T`), Saturation (`Y`/`U`), and Hue (`I`/`O`) with one-key reset (`Q`).
* **Video Frame Scaling & Zoom:** Interactive aspect ratio preservation, Pan & Scan, stretch-to-fit (`Ctrl+Enter`), 90° video rotation (`Alt+K`), mirror / invert flips (`Ctrl+Z`, `Ctrl+X`), and frame dimension scaling (`KP_8`/`KP_2`/`KP_6`/`KP_4`/`KP_5`/`KP_9`/`KP_1` or `Shift+Alt+Arrows`).

### 📸 Media Capture & Creation Studio
* **High-Resolution Frame Snapshots:** Save pristine full-resolution frames directly to disk (`Ctrl+P`) or via save dialog (`Ctrl+E`).
* **Clipboard Frame Copy (`Ctrl+C`):** Instantly copy the current video frame into the system clipboard for sharing in chat, documents, or image editors.
* **Animated GIF & WebP Creator (`Ctrl+Alt+G`):** Export lightweight animated clips from video segments with dual-pass palette generation for optimal color quality.
* **Storyboard Contact Sheet Generator:** Automatically construct a high-density thumbnail matrix sheet complete with video technical metadata and timecode stamps.
* **Live Ingestion:** Stream and display desktop screens (`Ctrl+S`) or webcam/V4L2 hardware capture devices (`Ctrl+J`).

### 🎨 Authentic Cairo DSF Skin Engine & Desktop UX
* **Native PotPlayer DSF Skin Support:** In-process Cairo unpacker that loads authentic `.dsf` skins and renders 9-slice button surfaces, active hover/pressed button states, progress timebars, and volume slider strips.
* **PotPlayer Right-Click Context Menu:** Exhaustive context menu matching PotPlayer's menu tree with dynamic audio/subtitle stream binding, aspect ratio presets, shader toggles, and panel dialogs.
* **Technical Playback Information HUD (`Tab`):** In-GPU OSD overlay displaying container bitrate, video/audio codecs, display aspect ratio, output FPS, dropped frame counters, and active hardware decoder status.
* **Playlist Window (`F8` / `F12`):** Multi-album tabbed playlist manager with drag-and-drop file ingestion, automatic directory scanning, smart alphanumeric sorting, and search.
* **Quick Control Box (`F6`):** Tabbed floating adjustment dialog consolidating Audio Equalizer, Video ProcAmp, Subtitle configuration, and Playback speed controls.
* **Smart Persistence:** SQLite backend (`mediadb.sqlite`) that automatically remembers resume positions, track selections, and bookmarks (`P`, `H`, `J`) across restarts.
* **Seamless A-B Repeat Loop (`Ctrl+[` / `Ctrl+]` / `Ctrl+\`):** High-precision video segment looping.
* **System Integration:** MPRIS2 D-Bus service (`org.mpris.MediaPlayer2.jonaki`) for system media keys and desktop environments, combined with single-instance IPC coordination (`/current`, `/new`).

---

## Architecture & Technical Design

### 1. In-Process C-FFI Core Engine
Earlier prototypes relying on external `mpv` subprocesses communicated over Unix domain JSON-IPC sockets. In practice, detached subprocesses introduced race conditions during rapid startup, dropped initial seek/subtitle configurations, and struggled with window reparenting under modern display servers.

Jonaki embeds `libmpv` directly in-process using Python `ctypes`:
* Direct C-API invocations eliminate socket serialization latency and IPC handshake overhead.
* Hardware-accelerated decoding pipelines (VA-API, NVDEC, VDPAU, Vulkan) render directly into the allocated X11/XWayland surface (`wid`).
* Enforces numeric C locale (`LC_NUMERIC="C"`) across glibc boundaries to prevent floating-point parsing discrepancies between GTK and `libmpv`.

### 2. Display Server & Surface Embedding
* Operates seamlessly across native X11 environments and Wayland sessions (via XWayland compatibility). Direct pure Wayland rendering via `mpv_render_context` / Wayland subsurfaces is on the development roadmap.
* Automatically forces `gpu-context=x11egl` to ensure OpenGL contexts bind reliably to the GTK window ID without spawning detached secondary render surfaces.
* Direct GPU OSD path routes high-priority notifications through `mpv`'s text pipeline, avoiding compositing flicker and Cairo buffer stalls.

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
* `python3-libtorrent` (or `pip install libtorrent`): Enables high-performance BitTorrent and Magnet URI video streaming (`Ctrl+M` / `/torrentdlg`).
* `yt-dlp`: Enables playback of arbitrary streaming URLs (YouTube, Vimeo, Twitch, HLS/DASH).
* `wl-clipboard` (Wayland) / `xclip` (X11): Enables URL and file path ingestion directly from the system clipboard (`/clipboard` or `Ctrl+U`).

---

## Installation

### Automated User Installation (Recommended)

Run the included installation script to link the launcher binaries and register desktop entries, MIME types, and high-resolution icons into `~/.local/`:

```bash
git clone https://github.com/ashik60/JonakiPlayer.git
cd JonakiPlayer
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

# Stream directly from a Magnet URI or torrent file
jonaki "magnet:?xt=urn:btih:..."

# Open file or torrent dialog at launch
jonaki /filedlg
jonaki /torrentdlg

# Force a standalone secondary process instead of delegating to existing instance
jonaki /new video.mp4

# Pipe a media stream from standard input
yt-dlp -o - -f best "https://www.youtube.com/watch?v=..." | jonaki -
```

### CLI Parameters Reference

| Parameter | Description |
| :--- | :--- |
| `[file / url / folder]` | Path, URL, or Magnet URI to enqueue and play immediately |
| `/seek=hh:mm:ss.ms` | Jump to specified timestamp upon opening |
| `/sub="path.srt"` | Load external subtitle file |
| `/aud="path.m4a"` | Load external audio stream |
| `/volume=0..100` | Set initial volume output |
| `/filedlg` | Open file chooser dialog on startup |
| `/folderdlg` | Open folder chooser dialog on startup |
| `/urldlg` | Open network stream entry dialog on startup |
| `/torrentdlg` | Open BitTorrent & Magnet streaming dialog on startup |
| `/clipboard` | Ingest and play media URL or local path from clipboard |
| `/new` | Force a new application process instance |
| `/current` | Delegate playback to running primary instance (default) |
| `-` | Read media stream from standard input (`stdin`) |
| `--help`, `-h`, `/?` | Display command-line parameter help |


---

## Keybindings Reference

### Playback & Playlist Navigation

| Keybinding | Action |
| :--- | :--- |
| `Space` | Toggle Playback (Play / Pause) |
| `F4` | Stop Playback / Close Current File |
| `Escape` | Exit Fullscreen (if in fullscreen) / Stop Playback |
| `Page Down` / `KP_Page_Down` | Play Next item in playlist |
| `Page Up` / `KP_Page_Up` | Play Previous item in playlist |
| `D` or `.` (Period) or `>` | Frame Step Forward (+1 frame) |
| `F` or `,` (Comma) or `<` | Frame Step Backward (-1 frame) |

### Seeking & Jump Intervals

| Keybinding | Action |
| :--- | :--- |
| `Left` / `Right` | Seek backward / forward 5 seconds |
| `Ctrl+Left` / `Ctrl+Right` | Seek backward / forward 30 seconds |
| `Shift+Left` / `Shift+Right` | Seek backward / forward 1 minute (60 sec) |
| `Ctrl+Alt+Left` / `Ctrl+Alt+Right` | Seek backward / forward 5 minutes (300 sec) |

### Playback Speed

| Keybinding | Action |
| :--- | :--- |
| `Z` | Reset Playback Speed to normal (1.0x) |
| `X` | Decrease Playback Speed (-0.1x) |
| `C` | Increase Playback Speed (+0.1x) |

### File, Stream & Device Ingestion

| Keybinding | Action |
| :--- | :--- |
| `Ctrl+O` / `F3` | Open Media File(s) dialog |
| `Ctrl+U` | Open Streaming URL dialog |
| `Ctrl+M` | Open BitTorrent / Magnet stream dialog |
| `Ctrl+V` | Open Media URL or file path from Clipboard |
| `F2` | Open Folder dialog |
| `Ctrl+S` | Open Screen Capture stream |
| `Ctrl+J` | Open Webcam / Video Device |

### Video Window, Aspect Ratio & Geometry

| Keybinding | Action |
| :--- | :--- |
| `Enter` / `KP_Enter` | Toggle Fullscreen |
| `Ctrl+Enter` | Toggle Stretch Video (Fit Window/Screen) / Keep Aspect Ratio |
| `V` | Cycle Aspect Ratio modes (Auto, 16:9, 4:3, 2.35:1, 1.85:1) |
| `Ctrl+T` | Toggle Always on Top (Stay on top) |
| `Alt+1` / `Alt+KP_1` | Window Preset: 50% (0.5x original resolution) |
| `Alt+2` / `Alt+KP_2` | Window Preset: 100% (1.0x original resolution) |
| `Alt+3` / `Alt+KP_3` | Window Preset: 150% (1.5x original resolution) |
| `Alt+4` / `Alt+KP_4` | Window Preset: 200% (2.0x original resolution) |
| `Alt+K` | Rotate Video 90° Clockwise |
| `Ctrl+Z` | Toggle Horizontal Flip (Mirror) |
| `Ctrl+X` | Toggle Vertical Flip (Invert) |
| `Ctrl+B` | Toggle Deband filter |
| `Ctrl+F11` | Toggle Deinterlacing filter |
| `Ctrl+H` | Toggle HDR Tone-Mapping |

### Video Frame Scaling & Zoom

| Keybinding (Numpad) | Keybinding (Laptop / Non-Numpad Alt) | Action |
| :--- | :--- | :--- |
| `KP_8` | `Shift+Alt+Up` | Increase Video Height (+5%) |
| `KP_2` | `Shift+Alt+Down` | Decrease Video Height (-5%) |
| `KP_6` | `Shift+Alt+Right` | Increase Video Width (+5%) |
| `KP_4` | `Shift+Alt+Left` | Decrease Video Width (-5%) |
| `KP_5` | `Shift+Alt+0` / `Alt+0` / `Ctrl+Alt+0` | Reset Video Dimensions & Zoom (100%) |
| `KP_9` / `KP_+` | `Shift+Alt+=` / `Alt+=` / `Ctrl+Alt+=` | Video Zoom In (+5%) |
| `KP_1` / `KP_-` | `Shift+Alt+-` / `Alt+-` / `Ctrl+Alt+-` | Video Zoom Out (-5%) |

### Video Colors & ProcAmp Adjustments

| Keybinding | Action |
| :--- | :--- |
| `Q` | Reset Video Colors (Brightness, Contrast, Saturation, Hue) |
| `W` / `E` | Brightness adjust (-1% / +1%) |
| `R` / `T` | Contrast adjust (-1% / +1%) |
| `Y` / `U` | Saturation adjust (-1% / +1%) |
| `I` / `O` | Hue adjust (-1° / +1°) |

### Audio Controls, Equalizer & Sync

| Keybinding | Action |
| :--- | :--- |
| `Up` / `Down` | Volume increment / decrement (+/- 2%) |
| `M` | Toggle Audio Mute |
| `Shift+Up` | Volume Boost PreAmp (+1 dB, up to +24 dB) |
| `Shift+Down` | Volume Boost PreAmp (-1 dB, down to 0 dB) |
| `Shift+N` | Toggle Auto Volume Normalizer (AVC) |
| `Shift+E` | Toggle Audio Enhancement (Loudness & Speech boost) |
| `A` | Cycle Audio Stream / Track |
| `Shift+[` | Audio Sync adjust (-50 ms / -0.05s) |
| `Shift+]` | Audio Sync adjust (+50 ms / +0.05s) |
| `Shift+\` | Reset Audio Sync to 0 ms |

### Subtitles & Dual Subtitle Tracks

| Keybinding | Action |
| :--- | :--- |
| `S` | Cycle Primary Subtitle Track |
| `Shift+S` | Cycle Secondary Subtitle Track (Dual Subtitles) |
| `Alt+O` | Open / Load Subtitle File |
| `Alt+H` | Toggle Subtitle Visibility (Show / Hide) |
| `[` / `]` | Subtitle Sync adjust (-0.5s / +0.5s) |
| `\` | Reset Subtitle Sync (0.0s) |
| `Alt+Left` / `Alt+Right` | Subtitle Sync adjust (-0.5s / +0.5s) |
| `Alt+/` | Reset Subtitle Sync (0.0s) |
| `Alt+PgUp` / `Alt+PgDn` | Subtitle Font Size adjust (+2 pt / -2 pt) |
| `Alt+Up` / `Alt+Down` | Subtitle Position adjust (Move Up / Down) |
| `Alt+Home` | Reset Subtitle Position to default (100%) |
| `Alt+T` | Toggle Real-Time AI Subtitle Translation |
| `Ctrl+Alt+S` | Search Subtitles Online (OpenSubtitles hash & text search) |

### A-B Repeat Loop & Bookmarks

| Keybinding | Action |
| :--- | :--- |
| `Ctrl+[` | Set Repeat Point A (Loop start) |
| `Ctrl+]` | Set Repeat Point B (Loop end) |
| `Ctrl+\` | Clear A-B Repeat Loop |
| `P` | Add Bookmark at current timestamp |
| `H` | Jump to Previous Bookmark |
| `J` | Jump to Next Bookmark |

### Frame Capture & Recording

| Keybinding | Action |
| :--- | :--- |
| `Ctrl+P` | Save Current Video Frame (Snapshot to default capture folder) |
| `Ctrl+E` | Save Current Video Frame As... (file dialog prompt) |
| `Ctrl+C` | Copy Current Video Frame to System Clipboard |
| `Ctrl+Alt+G` | Create Animated GIF / WebP clip from video |

### Dialogs, Panels & HUD

| Keybinding | Action |
| :--- | :--- |
| `Tab` | Toggle Technical Playback Info Overlay (In-GPU HUD) |
| `Ctrl+F1` | Open Media & Stream Properties Report |
| `F1` | Open About Jonaki Dialog |
| `F5` | Open Preferences Dialog |
| `F6` | Open Quick Control Box (Equalizer, Video ProcAmp, Subtitles) |
| `F7` | Open 10-Band Graphic Equalizer Window |
| `F8` / `F12` | Toggle Playlist Window |

### Mouse & Pointer Shortcuts

| Interaction | Action |
| :--- | :--- |
| `Left Click` (Single) | Toggle Playback (Play / Pause) |
| `Left Click` (Double) | Toggle Fullscreen |
| `Right Click` | Open Context Menu (anywhere on video, logo, control bar, or window) |
| `Mouse Scroll Up / Down` | Volume increment / decrement (+/- 2%) |
| `Click & Drag on Timebar` | Seek to percentage position across timeline |
| `Click & Drag on Volume Slider` | Set audio volume level |


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
