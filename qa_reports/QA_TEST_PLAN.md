# Jonaki Player — Comprehensive SQA Risk-Based Test Plan

**Document Version:** 1.0.0  
**Date:** 2026-10-27  
**Author:** Senior Software QA Engineer & Linux Desktop Application Tester  
**Repository:** `ashik60/JonakiPlayer` (`/home/ashik/Data/Projects/Jonaki`)  
**Target:** Linux Desktop Media Player (GTK 3 + In-Process libmpv C-FFI)  

---

## 1. Executive Overview & Scope

### 1.1 Purpose
This document establishes the risk-based quality assurance strategy and test plan for **Jonaki Player** (formerly Jonaki for Linux). Jonaki is a keyboard-driven, low-latency native Linux multimedia player designed to provide feature and workflow parity with Windows Jonaki by embedding `libmpv` directly in-process via Python C-FFI (`ctypes`) inside a GTK 3 drawing surface.

### 1.2 Test Scope
The audit spans all functional and non-functional dimensions of the application:
1. **Core Playback Engine**: In-process `libmpv` initialization, playback states (Play, Pause, Stop, Seek, EOF), speed manipulation (0.1x to 16.0x) with pitch correction, frame stepping, and A-B repeat looping.
2. **Media Compatibility & Error Handling**: Support across standard video and audio containers (MP4, MKV, WebM, AVI, TS, MP3, FLAC, Opus), embedded/external subtitles (SRT, ASS, VTT), unusual resolutions, high-framerate/8K video, zero-byte files, corrupted media, and missing files.
3. **User Interface & Control Surfaces**: DSF Cairo skin rendering, transport controls, timeline seeking, volume adjustment, keyboard shortcuts, HUD technical overlay (`Tab`), OSD notifications, and secondary dialogs (Control Box `F6`, Graphic Equalizer `F7`, Playlist `F8`/`F12`, Media Information `Ctrl+F1`, Subtitle Search `Ctrl+Alt+S`, About `F1`).
4. **Playlist & Navigation**: Item addition/removal, clearing, sorting, shuffling, search filtering, duplicate handling, missing file resilience, and drag-and-drop.
5. **MPV Integration Architecture**: In-process `wid` embedding, locale safety (`LC_NUMERIC="C"`), asynchronous property ticks (100ms), track selection, hardware acceleration binding (`vaapi`/`nvdec`/`auto`), and termination cleanup.
6. **Reliability & Resource Management**: Stress seeking, rapid file switching, long playback endurance, memory leak analysis, process monitoring, and clean shutdown without lingering threads or sockets.
7. **Linux Desktop Integration**: CLI switches (`/new`, `/current`, `/seek=`, `/volume=`, `/sub=`, `/aud=`, stdin `-`), Unix domain socket IPC single-instance coordinator, MPRIS2 D-Bus service, `.desktop` launcher registration, and installation scripts.
8. **Security & Data Integrity**: Path traversal checks, command execution safety in subprocesses, SQLite persistence (`~/.config/jonaki/mediadb.sqlite`), transaction integrity, and IPC payload validation.

---

## 2. Test Environment & Baseline Specification

| Component | Target Environment | Notes |
| :--- | :--- | :--- |
| **Operating System** | Debian GNU/Linux 13 (Trixie), x86_64 | Kernel 6.12.113+deb13-amd64 |
| **Display Protocol** | Wayland (Mutter/GNOME / KWin) & X11 | Tested under active XWayland (`DISPLAY=:1`, `WAYLAND_DISPLAY=wayland-0`) |
| **GUI Framework** | GTK 3 (3.24.43+), PyGObject (python3-gi 3.48+), PyCairo | Enforced `GDK_BACKEND=x11` for direct `wid` X11 surface binding |
| **Media Core** | In-Process `libmpv.so.2` (v0.40.0, API 2.5) | Packed in `lib/libmpv.so.2.5.0`, zero external runtime dependency |
| **System FFmpeg** | FFmpeg 7.1.2-0+deb13u1 (libavcodec 61.19.101) | Underlying demuxer and decoder libraries |
| **Python Runtime** | Python 3.13.5 (standard library `unittest`) | Standard interpreter |
| **Persistence** | SQLite 3 (`~/.config/jonaki/mediadb.sqlite`) | WAL journal mode, automatic schema migrations |
| **IPC Mechanism** | Unix Domain Socket (`$XDG_RUNTIME_DIR/jonaki_ipc.sock`) | Advisory file locking (`.lock`) + JSON framed line protocol |

---

## 3. Risk Assessment & Priority Matrix

| Risk ID | Hazard / Failure Mode | Probability | Impact | Severity | Mitigation Strategy |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **RSK-01** | Window surface decoupling under Wayland spawning separate MPV window | Medium | Critical | High | Validate `GDK_BACKEND=x11`, unsetting `WAYLAND_DISPLAY`, and explicit `set_wid()` timing. |
| **RSK-02** | Race conditions during rapid playback/seek/stop operations | High | High | High | Stress-test event queue and asynchronous `_query_time_tick` callbacks. |
| **RSK-03** | Crashes due to `None` or `NaN` values returned by MPV properties | High | High | High | Defensive coalescing across OSD, HUD, time formatters, and MediaInfo dialogs. |
| **RSK-04** | Memory leaks or GSource timer leaks during extended sessions | Medium | High | Medium | Profile RSS/VMS memory and source IDs during repetitive file switching. |
| **RSK-05** | IPC socket hijacking, TOCTOU socket unlinking, or malformed payloads | Medium | High | High | Audit advisory file lock (`flock`), permission masks (0700), and payload size limits. |
| **RSK-06** | UI freezing or deadlocks when executing background tasks (translation/search) | Medium | Medium | Medium | Verify worker thread isolation and GTK dispatch via `GLib.idle_add`. |
| **RSK-07** | Media database corruption or schema migration failure | Low | High | Medium | Comprehensive unit testing of SQLite transactions and rollback behavior. |

---

## 4. Test Suite Structure & Coverage Areas

```
tests/
├── corpus/                             # Synthesized reproducible media edge-case corpus
│   ├── valid_h264_aac.mp4              # Standard baseline media
│   ├── valid_vp9_opus.webm             # Modern open-standards media
│   ├── audio_only.mp3 / .flac          # Audio-only streams
│   ├── video_only_hevc.mkv             # Video-only streams
│   ├── multi_audio_tracks.mkv          # Multi-audio stream routing
│   ├── movie_with_subs.mkv             # Embedded subtitles
│   ├── subtitles_sample.srt/.ass/.vtt  # External subtitle formats
│   ├── corrupted_header.mp4            # Truncated corrupt media
│   ├── empty_file.mp4                  # 0-byte boundary file
│   └── unicode_and_special_chars.mkv   # Path safety test file
├── test_cli.py                         # CLI switch parser verification
├── test_cursor_and_controls.py         # Mouse cursor auto-hide and fullscreen controls
├── test_engine.py                      # Libmpv core engine unit tests
├── test_equalizer.py                   # 10-band graphic equalizer & DSP math
├── test_ipc.py                         # Single-instance IPC protocol & locking
├── test_media_db.py                    # SQLite resume database & bookmarks
├── test_playlist_view.py               # Playlist filtering, sorting, shuffling
├── test_skin_engine.py                 # DSF Cairo skin blitter & hit-testing
├── test_subtitle_and_mpris.py          # MPRIS2 D-Bus & Subtitle coordination
├── test_audit_fixes.py                 # Fix verification regression suite
├── test_ui_audit_fixes.py              # UI interaction regression suite
├── test_playback_integration.py        # Real media playback & codec integration tests
├── test_ui_comprehensive.py            # Deep UI button, menu, dialog interaction tests
└── test_systems_and_security.py        # Security, stress, and desktop integration tests
```

---

## 5. Pass / Fail & Exit Criteria

1. **Pass Criteria**:
   - 100% of P0 (Release-Blocking) and P1 (High) test cases must pass.
   - Zero application crashes, segmentation faults, or uncaught exceptions during normal workflows.
   - In-process video rendering binds cleanly without detached secondary windows.
   - Real media playback verified across MP4, MKV, WebM, FLAC, MP3, and 8K AV1.
   - All automated unit and integration tests execute successfully with deterministic results.
2. **Fail Criteria**:
   - Any crash or unhandled exception during standard media loading, seeking, or window manipulation.
   - Detached MPV window spawning on Wayland or X11 desktops.
   - Resource leaks causing monotonically increasing memory or leaked child processes.
   - Security vulnerabilities allowing arbitrary command injection or unauthorized file access.
3. **Blocked Criteria**:
   - Tests requiring hardware features not present in the test environment (e.g. dedicated hardware TV tuners).
