# Technical Audit & Remediation Report: Jonaki (PotPlayer Linux Rewrite)

**Target Codebase:** Jonaki Multimedia Player (formerly PotPlayer Linux rewrite)  
**Evaluated Environment:** Linux x86_64, GTK 3.24, Python 3.13 / 3.12, libmpv 0.40.0, libtorrent 2.0  
**Test Suite Verification:** 349 / 349 tests passing (100% pass rate)

---

## 1. Executive Summary

A comprehensive architectural, code quality, and user experience audit was performed on the Jonaki codebase created by Claude. The codebase provides a feature-rich, native Linux desktop multimedia player inspired by Daum PotPlayer, featuring a custom DSF Cairo-rendered skin engine, libmpv backend, PipeWire/PulseAudio low-latency audio DSP, GLSL video post-processing, SQLite-backed media history, and libtorrent sequential streaming.

While the overall architecture is well-structured and separation of concerns is clean, the audit identified several **critical functional bugs**, **hallucinated QA defect entries**, **silent data loss risks**, **dead UI event handlers**, and **significant UX gaps**.

All identified defects have been resolved and verified against the complete test suite.

```
Total Test Cases:    349
Tests Passed:        349 (100%)
Failures / Errors:   0
Resolved Defects:    15 major/minor issues across Core, UI, Subtitles, Audio, and Scripts
```

---

## 2. Key Findings & Bug Audit

### 2.1 Critical Hallucinated QA Defect: DEF-PLY-03
- **Location:** [`src/core/engine.py`](file:///home/ashik/Data/Projects/PotPlayer/src/core/engine.py#L442-L465) & [`qa_reports/QA_DEFECTS.md`](file:///home/ashik/Data/Projects/PotPlayer/qa_reports/QA_DEFECTS.md#L156-L169)
- **Defect Description:** In `QA_DEFECTS.md`, defect `DEF-PLY-03` (*"`play()` and `play_pause()` transition state to `PLAYING` without file loaded"*) was documented and marked as **"Resolved & Verified"**, citing regression test `tests/test_playback_integration.py:TC-PLY-08`.
- **Audit Discovery:** 
  1. Inspection of `TC-PLY-08` revealed that it actually tests playback speed boundary clamping between 0.1x and 16.0x, completely unrelated to `DEF-PLY-03`.
  2. The guard in `src/core/engine.py` was **never implemented**. Calling `core.play()` or `core.play_pause()` without a file loaded transitioned `core.state` into `PlaybackState.PLAYING`, emitted 10Hz timer ticks, hid the idle logo, and blanked the screen.
  3. `tests/test_engine.py:295` explicitly asserted the broken behavior (`self.core.play(); self.assertEqual(self.core.state, PlaybackState.PLAYING)` with no file loaded).
- **Remediation:** Added `if not self.current_file: return` guard to `play()`, `pause()`, and `play_pause()`. Updated `test_engine.py` to verify that `play()` without a file safely retains `PlaybackState.IDLE`, and verified subsequent valid playback transitions.

---

### 2.2 Fatal Media Loading Failure on Paths with Commas
- **Location:** [`src/core/engine.py:424-436`](file:///home/ashik/Data/Projects/PotPlayer/src/core/engine.py#L424-L436)
- **Defect Description:** When loading files with sidecar subtitle or audio files, options were appended as unquoted strings: `opts.append(f"sub-file={sub_file}")` and passed to `mpv_command("loadfile", resolved, "replace", "-1", ",".join(opts))`.
- **Impact:** In libmpv, `,` is the option delimiter. Any media file or folder containing commas (e.g. `Movie, The [2024]/video.mp4` or sibling subtitle `Movie, The.srt`) caused mpv option parsing to fail with code `-4` (Invalid Parameter). The video failed to load completely.
- **Remediation:** Added path sanitization and quoting for options containing commas or whitespace:
  ```python
  if sub_file:
      safe_sub = sub_file.replace('"', '\\"')
      opts.append(f'sub-file="{safe_sub}"' if (',' in safe_sub or ' ' in safe_sub) else f"sub-file={safe_sub}")
  ```

---

### 2.3 Data Loss: Silent Subtitle Overwrites
- **Location:** [`src/ui/subtitle_search_dialog.py:308-325`](file:///home/ashik/Data/Projects/PotPlayer/src/ui/subtitle_search_dialog.py#L308-L325)
- **Defect Description:** When downloading subtitles from online search providers (OpenSubtitles / Subscene), the file was unconditionally saved as `os.path.join(video_dir, f"{base_name}.{ext}")`.
- **Impact:** If the user already had a local subtitle file or was downloading alternate translations (e.g. English + Spanish), the existing subtitle was destroyed and overwritten without confirmation.
- **Remediation:** 
  1. Incorporated the track's language code into the filename (`{base_name}.{lang}.{ext}`).
  2. Implemented non-destructive collision resolution (appending numeric counters `.{counter}.ext` if a matching file already exists).

---

### 2.4 Video Zoom & Distortion Leakage Across Media
- **Location:** [`src/core/engine.py:400-475`](file:///home/ashik/Data/Projects/PotPlayer/src/core/engine.py#L400-L475)
- **Defect Description:** When a user adjusted video dimensions (zoom, aspect stretch, height/width scaling via `NumPad +/-`), the values remained active in `libmpv` indefinitely.
- **Impact:** Opening a new media file or stopping and starting another video caused the new media to play distorted or cropped with previous zoom/scale offsets.
- **Remediation:** Added automatic dimension reset (`self.reset_video_dimensions()`) during `load_file()` and `stop()`.

---

### 2.5 Unhandled Module Import Crash in Subtitle Translator
- **Location:** [`src/subtitle/translator.py:72`](file:///home/ashik/Data/Projects/PotPlayer/src/subtitle/translator.py#L72)
- **Defect Description:** `import threading` was placed inside `__init__()` rather than module-level scope. Calling `clear_cache()` directly on the module or instance risked `NameError: name 'threading' is not defined`.
- **Remediation:** Lifted `import threading` to module top-level.

---

### 2.6 Silent Capture Failures Without User Feedback
- **Location:** [`src/ui/main_window.py:1530-1565`](file:///home/ashik/Data/Projects/PotPlayer/src/ui/main_window.py#L1530-L1565)
- **Defect Description:** Triggering frame snapshot (`Ctrl+E`, `Ctrl+C`), animated GIF (`Ctrl+Alt+G`), or Storyboard creation when no video was loaded failed silently with no indication to the user.
- **Remediation:** Added explicit state guards with clear OSD error toasts: `"Capture Failed: No active media"`.

---

## 3. UI / UX Glitches & Improvements

| Area | Component | Issue Identified | Resolution Implemented |
| :--- | :--- | :--- | :--- |
| **DSF Skin Bar** | [`skin_engine.py`](file:///home/ashik/Data/Projects/PotPlayer/src/ui/skin_engine.py#L210-L225) | Clicking codec badges (`AV1`, `OPUS`, `2.0ch`) fired commands unhandled in `main_window.py`. | Bound `CMD_VIDEO_CODEC_FOURCC_MESSAGE` to Media Info Dialog, `CMD_AUDIO_CODEC_TYPE_MESSAGE` to cycle audio tracks, and `CMD_AUDIO_OUT_NUM_CHANNEL_MESSAGE` to Audio Control Box. |
| **DSF Skin Bar** | [`main_window.py`](file:///home/ashik/Data/Projects/PotPlayer/src/ui/main_window.py#L180-L192) | Mouse scroll wheel was ignored over the bottom skin bar and volume slider. | Added `Gdk.EventMask.SCROLL_MASK` and connected `_on_skin_scroll`. Scrolling over timebar seeks relative (±5s); scrolling over buttons/slider adjusts volume. |
| **DSF Skin Bar** | [`main_window.py`](file:///home/ashik/Data/Projects/PotPlayer/src/ui/main_window.py#L770-L775) | Hovering cursor over the volume slider showed no tooltip. | Added live tooltip display: `Volume: X%`. |
| **Playlist** | [`playlist_view.py`](file:///home/ashik/Data/Projects/PotPlayer/src/ui/playlist_view.py#L115-L135) | Double-clicking a track or track change cleared the search filter while query text remained in search box. | `update_playlist()` now checks for an active query and preserves the filtered view. |
| **Playlist** | [`playlist_view.py`](file:///home/ashik/Data/Projects/PotPlayer/src/ui/playlist_view.py#L125-L130) | Active track was indicated only by `▶ ` text; TreeView never selected or auto-scrolled to the row. | Implemented auto-selection and `scroll_to_cell()` centering the active item in view. |
| **Playlist** | [`playlist_view.py`](file:///home/ashik/Data/Projects/PotPlayer/src/ui/playlist_view.py#L76-L85) | No "Clear" button; no right-click context menu in the list. | Added "Clear" button and context menu with Play, Remove, and Clear All options. |
| **Control Box** | [`control_box.py`](file:///home/ashik/Data/Projects/PotPlayer/src/ui/control_box.py#L240-L255) | Selecting an Equalizer preset activated the backend filter but left the "Enable Equalizer" checkbutton unchecked. | Synchronized checkbutton state `self.eq_check.set_active(True)` in preset callback. |
| **Control Box** | [`control_box.py`](file:///home/ashik/Data/Projects/PotPlayer/src/ui/control_box.py#L360-L375) | No quick way to reset playback speed to 1.0x in the Playback tab. | Added "Reset Speed (1.0x)" button beside the speed slider. |
| **Window Sizing**| [`main_window.py`](file:///home/ashik/Data/Projects/PotPlayer/src/ui/main_window.py#L1680-L1698) | `Alt+1..4` on 4K/8K media enlarged window far beyond monitor workarea boundaries. | Added `_resize_clamped()` using monitor geometry to prevent offscreen window spillover. |
| **Context Menu** | [`context_menu.py`](file:///home/ashik/Data/Projects/PotPlayer/src/ui/context_menu.py#L70-L115) | Missing entries for "Stay on Top", "A-B Repeat", and "Window Size" presets. | Added "Stay on Top \tCtrl+T", "A-B Repeat" submenu, and "Window Size" submenu with checkmarks. |
| **OSD HUD** | [`osd_overlay.py`](file:///home/ashik/Data/Projects/PotPlayer/src/ui/osd_overlay.py#L120-L125) | Monospace file path string spilled outside HUD box on narrow windows. | Calculated `max_chars` dynamically based on card width. |
| **OSD HUD** | [`main_window.py`](file:///home/ashik/Data/Projects/PotPlayer/src/ui/main_window.py#L1580-L1585) | Setting Aspect Ratio to Auto displayed `"Aspect Ratio: -1"`. | Translated `"-1"` to `"Auto (Default)"`. |

---

## 4. Script & Packaging Portability Audit

1. **Dynamic Python Version Detection in `bin/jonaki`**:
   - `bin/jonaki` hardcoded `$HOME/.local/lib/python3.13/site-packages`.
   - On distributions shipping Python 3.12 (e.g. Ubuntu 24.04 LTS) or Python 3.11 (Debian 12), user-installed packages were omitted from `PYTHONPATH`.
   - Updated launcher with dynamic minor-version detection:
     ```bash
     PY_VER="$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null || echo "3")"
     export PYTHONPATH="$PROJECT_DIR/src:$HOME/.local/lib/python${PY_VER}/site-packages:$PYTHONPATH"
     ```
2. **PotPlayer Symlink & Installation Parity**:
   - Re-established `bin/potplayer` symlink to `bin/jonaki`.
   - Updated `install.sh` and `uninstall.sh` to install and remove both `jonaki` and `potplayer` symlinks in `~/.local/bin/`.
3. **Deprecation Cleanup**:
   - Replaced deprecated `set_wmclass` with standard `GLib.set_prgname("jonaki")` and `GLib.set_application_name("Jonaki")` with multi-call guards.
   - Replaced deprecated `Gdk.Screen.get_width()` with `Gdk.Monitor.get_geometry()` display querying.

---

## 5. Verification & Regression Analysis

All 349 unit and integration tests across the test suite were executed:

```bash
$ python3 -m unittest discover -s tests
----------------------------------------------------------------------
Ran 349 tests in 60.427s

OK
```

All test suites passed with zero regressions:
- `tests/test_engine.py`: Core libmpv lifecycle, state machine, property querying, seeking, and track selection.
- `tests/test_playback_integration.py`: High-concurrency playback, speed scaling, EOF advancement, and track switching.
- `tests/test_ui_comprehensive.py`: Window lifecycle, keybindings, skin rendering, mouse interactions, and dialog controllers.
- `tests/test_ui_audit_fixes.py`: Hit-testing, volume sliders, equalizer synchronization, and menu dispatch.
- `tests/test_playlist_view.py`: Duration formatting, search filtering, index mapping, and reordering.
- `tests/test_torrent_streaming.py`: Magnet URI validation, file mapping, deadline prioritization, and streaming sessions.
- `tests/test_audio_enhancement.py`: 10-band equalizer, normalizer, and audio DSP chain.
- `tests/test_subtitle_and_mpris.py`: Subtitle search, synchronization, AI translation, and MPRIS2 D-Bus interface.
- `tests/test_systems_and_security.py`: IPC socket security, path traversal guards, and SQLite corruption resilience.
