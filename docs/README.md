# Jonaki: Engineering Architecture & Implementation Documentation

Welcome to the comprehensive engineering documentation for **Jonaki** (formerly *Jonaki for Linux*) — an open-source, pixel-accurate, feature-complete media player designed natively for Linux environments (X11, Wayland, PipeWire, PulseAudio, and ALSA), inspired by Daum/Kakao Jonaki.

---

## 1. Executive Summary & Objective

Jonaki for Windows is widely recognized as one of the most flexible, performant, and feature-rich media players in the world. It provides unparalleled hardware acceleration capabilities, an advanced modular DirectShow-based filter graph, an extensive subtitle processing and real-time AI translation suite, a pixel-shader post-processing pipeline, an extensible AngelScript plugin system, and a completely custom-skinnable UI (`.dsf` format).

The objective of this project is to:
1. **Reverse engineer** the Windows Jonaki distribution (`JonakiSetup64.exe`, version 26.10.21.0 / 1.7.23159), including its binary structure, RTTI class hierarchy, resource dictionaries, `.ini` localization maps, AngelScript extensions, `.dsf` skins, HLSL pixel shaders, and command-line interfaces.
2. **Design and implement** a native Linux player architecture that replicates every single capability, UI interaction, shortcut key, command-line parameter, and extension point of the original Jonaki.
3. **Bridge Linux multimedia primitives** (FFmpeg 7.x, `libmpv`/`mpv` IPC, `libplacebo`, Vulkan/OpenGL, VA-API/NVDEC, PipeWire, and MPRIS2) to provide the same high performance and zero-copy rendering as DirectShow/DXVA2/D3D11 on Windows.

---

## 2. Windows Artifact Reverse-Engineering Inventory

Extracted directly from `JonakiSetup64.exe` using REA (Reverse Engineer Anything) methodologies:

| Windows Binary / Asset | Size | Purpose in Windows Jonaki | Linux Native Replacement / Implementation Strategy |
| :--- | :--- | :--- | :--- |
| `Jonaki64.dll` | 35.3 MB | Core player engine, DirectShow filter graph, UI controls, skin rendering engine | High-performance Python/GTK4/C core engine with MPV/FFmpeg backend |
| `Jonaki64.exe` / `JonakiMini64.exe` | 2.5 MB | Entry launcher, process single-instance lock, CLI parameter parser | Python/CLI wrapper supporting 100% of `CmdLine64.txt` switches |
| `ffcodec64.dll` | 38.1 MB | Customized FFmpeg fork for demuxing, video/audio decoding & software scaling | Native Linux `ffmpeg` / `libavcodec.so.61` / `libavformat.so.61` |
| `ATextOut64.dll` | 2.5 MB | Advanced subtitle rasterization engine (ASS/SSA, SAMI, SRT, VobSub, PGS) | `libass` + Cairo/Pango text rasterizer + real-time subtitle translation layer |
| `MediaDB64.dll` | 6.6 MB | SQLite/embedded media database for playlist history, bookmarks, and album tags | SQLite3 database engine (`~/.config/jonaki/mediadb.sqlite`) |
| `Module/MediaInfo64.dll` | 6.8 MB | Media container and codec metadata inspector | `mediainfo` / FFprobe stream analyzer |
| `Module/Whisper/Vulkan/*` | 4.5 MB | Local real-time speech-to-text subtitle generation using Vulkan compute | Whisper.cpp / Vulkan or ONNX Runtime STT backend |
| `Skins/Default.dsf` | 417 KB | Zip archive with XML/TXT layout & PNG sprites for player interface | Native `.dsf` ZIP parser & Cairo/GTK sprite/9-slice renderer |
| `Extension/api.txt` & `*.as` | 100+ KB | AngelScript runtime for subtitle translation, subtitle search, and stream parsing | Dual AngelScript/Python plugin runtime with `Host*` API emulation |
| `PxShader/*.txt` | 34 shaders | HLSL pixel shaders (Sharpen, ProcAmp, Adaptive Sharpen, Denoise, Levels) | GLSL / mpv user shader pipeline via `libplacebo` |
| `Language/English.ini` | 165 KB | 5,685 strings covering all menus, dialogs, IDs, and keybindings | Complete localization database and command dispatch dictionary |
| `CmdLine64.txt` | 51 KB | Complete command-line documentation in multiple codepages (CP0, CP949, etc.) | Standardized Linux CLI parser (`jonaki [files...] [options]`) |

---

## 3. Comprehensive Documentation Map

This documentation suite is organized into modular specifications covering every architectural layer:

1. **[System Architecture](ARCHITECTURE.md)**:
   - Comparison of Windows DirectShow graph vs. Linux multimedia stacks.
   - Core playback pipeline, process model, and threading architecture.
   - Video rendering (Wayland/X11, EGL, OpenGL, Vulkan, VA-API/VDPAU/NVDEC).
   - Audio routing (PipeWire, PulseAudio, ALSA bit-perfect output).
   - Inter-process communication (IPC) and desktop integration.

2. **[Features Specification](FEATURES_SPECIFICATION.md)**:
   - Complete inventory of all Jonaki playback capabilities.
   - Video processing, deinterlacing, color adjustment, 360° VR.
   - Audio processing, 10-band equalizer, normalizer, surround downmixing.
   - Subtitle engine, multi-subtitle tracks, AI translation, Whisper STT.
   - Bookmarks, A-B repeat, playlist management, contact sheets, GIF capture.
   - Complete keyboard shortcut reference matching Windows defaults.

3. **[Skin Engine Specification](SKIN_ENGINE_SPECIFICATION.md)**:
   - Format of `.dsf` skin files (ZIP containers with XML/TXT and sprites).
   - Syntax of layout descriptors (`BottomVideo.txt`, `Common.txt`, etc.).
   - Coordinate-based sprite extraction, 9-slice button rendering, and slider states.
   - Dynamic UI badges (`[HW]`/`[SW]`, `[HDR]`, `[H264]`, `[2.0]`, time labels).
   - OSD (On-Screen Display) positioning, typography, and seekbar overlays.

4. **[Subtitle Engine & AI Translation Specification](SUBTITLE_ENGINE_SPECIFICATION.md)**:
   - Subtitle format support (ASS, SSA, SRT, SMI/SAMI, VTT, PGS, SUP).
   - Multi-track simultaneous subtitle rendering (primary, secondary, tertiary).
   - Real-time online translation plugins (Google, DeepL, Papago, Bing, Libre, LM Studio).
   - Real-time local Whisper Vulkan / CPU speech recognition subtitle generator.
   - Online subtitle scrapers and synchronizers.

5. **[CLI & IPC Specification](CLI_AND_IPC_SPECIFICATION.md)**:
   - Full command-line option parity with `CmdLine64.txt`.
   - Single-instance IPC socket protocol (handling `/new`, `/current`, `/add`).
   - MPRIS2 D-Bus interface for Linux desktop media key and lockscreen control.
   - JSON-RPC external control API.

6. **[Extension API Specification](EXTENSION_API_SPECIFICATION.md)**:
   - Jonaki `Host*` built-in AngelScript API reverse engineering.
   - Media playback scrapers (`MediaPlayParse` - YouTube, Vimeo, custom streams).
   - Subtitle translation plugins (`SubtitleTranslate`).
   - Subtitle search plugins (`SubtitleSearch`).
   - Python plugin compatibility layer.

7. **[Pixel Shaders & VapourSynth](PIXEL_SHADERS_AND_VAPOURSYNTH.md)**:
   - Reverse-engineered HLSL shaders from `PxShader/` converted to GLSL.
   - Real-time post-processing shader pipeline.
   - VapourSynth and AviSynth motion interpolation scripts (`motioninterpolation.vpy`).

8. **[Linux Development & Build Guide](LINUX_DEVELOPMENT_GUIDE.md)**:
   - Development environment setup on Debian/Ubuntu, Fedora, and Arch Linux.
   - Repository layout, build instructions, and running the player.
   - Packaging into AppImage, Flatpak, and `.deb`.
