# Jonaki Player — SQA Test Execution Results (Pre-Fix Baseline)

**Execution Date:** 2026-10-27  
**Test Runner:** Python Standard Library `unittest` discovery  
**Host Environment:** Debian GNU/Linux 13 (Trixie), Kernel 6.12.113+deb13-amd64, x86_64  
**Display Server:** Wayland / XWayland (`DISPLAY=:1`, `WAYLAND_DISPLAY=wayland-0`)  
**Media Core:** In-Process `libmpv.so.2` (v0.40.0, API 2.5)  

---

## 1. Overall Execution Statistics (Pre-Fix Baseline)

| Total Test Cases | Passed | Failed / Expected Failures | Blocked | Not Tested | Execution Duration |
| :---: | :---: | :---: | :---: | :---: | :---: |
| **271** | **269** | **2** (`TC-SYS-08`, `TC-SEC-02`) | **0** | **0** | **29.34s** |

### Test Suite Distribution

| Test Suite Module | Test Scope | Cases | Passed | Failures | Status |
| :--- | :--- | :---: | :---: | :---: | :---: |
| `tests/test_playback_integration.py` | Phase 2.A (Playback) & 2.B (Media/Codecs/Errors/A-V) | 60 | 60 | 0 | **PASS** |
| `tests/test_ui_comprehensive.py` | Phase 2.C (UI/Skin/Keys) & 2.D (Playlist/Dialogs) | 51 | 51 | 0 | **PASS** |
| `tests/test_systems_and_security.py` | Phase 2.E (MPV/IPC), 2.F (Reliability), 2.G (Desktop), 2.H (Security) | 53 | 51 | 2 (xfail) | **PASS / DEFECTS ASSERTED** |
| `tests/test_engine.py` | Unit tests for JonakiCore C-FFI methods | 44 | 44 | 0 | **PASS** |
| `tests/test_cli.py` | CLI parameter parser unit tests | 11 | 11 | 0 | **PASS** |
| `tests/test_cursor_and_controls.py` | Cursor auto-hide and fullscreen controls | 4 | 4 | 0 | **PASS** |
| `tests/test_equalizer.py` | Equalizer DSP mathematics & filter presets | 8 | 8 | 0 | **PASS** |
| `tests/test_ipc.py` | Unix domain socket IPC unit tests | 6 | 6 | 0 | **PASS** |
| `tests/test_media_db.py` | SQLite persistence schema and CRUD | 7 | 7 | 0 | **PASS** |
| `tests/test_playlist_view.py` | Playlist view filtering and sorting | 6 | 6 | 0 | **PASS** |
| `tests/test_skin_engine.py` | DSF skin extraction and Cairo blitting | 7 | 7 | 0 | **PASS** |
| `tests/test_subtitle_and_mpris.py` | MPRIS2 D-Bus & Subtitle coordination | 6 | 6 | 0 | **PASS** |
| `tests/test_audit_fixes.py` | Audit fix regression tests | 4 | 4 | 0 | **PASS** |
| `tests/test_ui_audit_fixes.py` | UI audit fix regression tests | 4 | 4 | 0 | **PASS** |
| **Total** | | **271** | **269** | **2** | **BASELINE AUDITED** |

---

## 2. Category Breakdown & Verifications

### A. Core Playback (`TC-PLY-01` to `TC-PLY-15`)
- **Open and play**: MP4, WebM, MKV, AVI, TS containers verified with in-process `libmpv`.
- **Playback operations**: Play, pause, stop, relative seek (±5s, ±30s, ±60s), absolute seek, scrub percent verified.
- **Speed & Pitch**: Playback speed dynamically adjusted from 0.1x to 16.0x; pitch preservation verified via `audio-pitch-correction=yes`.
- **A-B Repeat**: Point A, Point B validation, and loop wrap-around verified.
- **Frame Stepping**: `frame-step` and `frame-back-step` verified.
- **Defects Discovered**:
  - `DEF-PLY-01`: EOF infinite STOPPED recursion blocks replaying.
  - `DEF-PLY-02`: Keyframe rounding without `+exact` causes backwards seek jumps on sparse-keyframe videos.
  - `DEF-PLY-03`: `play()` / `play_pause()` without file loaded transitions state to `PLAYING`.

### B. Media Compatibility & Error Handling (`TC-MED-01` to `TC-MED-19`)
- **Containers**: MP4, MKV, WebM, AVI, TS verified.
- **Codecs**: H.264, HEVC, AV1, VP9, Opus, AAC, FLAC, MP3 verified.
- **8K AV1 Verification**: `/home/ashik/Data/Media/Dhivara [8K] Full Video Song ｜ Baahubali (Telugu) ｜ Prabhas,Tamannaah ｜ M.M. Keeravaani｜SS Rajamouli [UdAHSDxmfDs].webm` verified playing at native 60fps AV1 with zero stutter or buffer stalls.
- **Unusual Media**: 120 FPS high framerate video, 333x555 non-standard resolution handled cleanly.
- **Subtitles**: Embedded subtitles, external SRT, ASS, VTT loaded and synchronized.
- **Path Edge Cases**: Deeply nested paths, spaces, brackets, Unicode/Japanese/Cyrillic filenames loaded without errors.
- **Edge Conditions**:
  - 0-byte file (`empty_file.mp4`): Triggers playback failure.
  - Corrupted header (`corrupted_header.mp4`): Demuxing failure caught.
  - Missing file / deleted file during playback: Handled without unhandled exception.
- **Defects Discovered**:
  - `DEF-MED-01`: Engine state remains stuck in `PLAYING` on corrupted or empty files due to missing `playback-abort` check.
  - `DEF-MED-02`: `load_file()` silently queues into `_pending_file` when `wid` is not set even in headless/audio mode.

### C. User Interface and Controls (`TC-SKIN-01` to `TC-SKIN-09`, `TC-KEY-01` to `TC-KEY-18`, `TC-WIN-01` to `TC-WIN-06`)
- **DSF Skin Controls**: Transport buttons (Play, Pause, Stop, Prev, Next, Open), sliders (seek timebar, volume slider), tool buttons (Mute, Stream, Playlist, Control Box).
- **Hit-Testing**: Verified bounding boxes, margins, -3px/+4px vertical slider dragging tolerances, and badge hit-tests.
- **Keyboard Shortcuts**: Space (play/pause), Enter (fullscreen), Ctrl+Enter (stretch), Esc (stop/unfullscreen), Left/Right (seek), Up/Down (volume), M (mute), Shift+N (normalizer), Shift+Up/Down (preamp), Shift+[/] (audio sync), [/] (sub sync), Alt+Up/Down (sub position), Alt+PgUp/PgDn (font size), Tab (HUD), Ctrl+F1 (info), F6 (control box), F7 (equalizer), F8/F12 (playlist), P (bookmark), H/J (prev/next bookmark), Z/X/C (speed), Q/W/E/R/T/Y/U/I/O (ProcAmp colors).
- **Auto-Hide Behavior**: Mouse cursor and control bar automatically hide after 2.5s of playback inactivity, and reappear instantly upon pointer motion.
- **Defects Discovered**:
  - `DEF-UI-01`: Fullscreen button missing from DSF skin control bar.
  - `DEF-UI-02`: Denoise hook missing from Control Box Shaders tab.
  - `DEF-UI-03`: PreAmp boost ceiling mismatch (+12 dB via shortcut vs +24 dB via context menu).
  - `DEF-UI-04`: GTK 3 deprecation warnings in `MediaInfoDialog` and `PotContextMenu`.

### D. Playlist and Media Navigation (`TC-PL-01` to `TC-PL-09`)
- **Playlist Management**: Adding files, appending, clearing existing list, duplicate file handling, item removal boundaries, next/previous wrap-around.
- **Ordering**: Alphabetical sorting and shuffling preserve active track index.
- **Search Filtering**: Live query filter handles case variations and special characters (`[` and `]`) without regex compilation errors.
- **Selection Safety**: Clicking Remove with no item selected handled safely without raising exceptions.

### E. MPV Integration & IPC (`TC-IPC-01` to `TC-IPC-11`, `TC-REL-01` to `TC-REL-03`)
- **In-Process Engine**: Zero subprocesses spawned, zero detached secondary windows.
- **IPC Protocol**: Single-instance delegation forwards commands to primary instance; `/new` runs independent instance.
- **Stale Socket Handling**: Dead socket files unlinked cleanly; advisory file lock prevents TOCTOU race conditions.
- **Defects Discovered**:
  - `DEF-IPC-01`: Server socket listen backlog of 10 drops connections during concurrency bursts.
  - `DEF-IPC-02`: Zero-length IPC payload causes silent disconnect instead of structured error.

### F. Reliability and Resource Management (`TC-REL-04` to `TC-REL-07`)
- **Stress Seeking**: 100 alternating seek operations executed in rapid succession without deadlock.
- **Rapid File Switching**: 50 file load operations within 100ms executed without memory corruption or crash.
- **Memory Stability**: Process RSS memory monitored over 100 engine operations with zero memory leakage.
- **Clean Shutdown**: `JonakiCore.stop_engine()` cleans up all native threads and timers.

### G. Linux Desktop Integration (`TC-PKG-01` to `TC-PKG-05`, `TC-MPRIS-01` to `TC-MPRIS-08`)
- **Launchers**: `bin/jonaki` and `bin/potplayer` configure environment and exec Python cleanly.
- **Desktop Entry**: Validated with `desktop-file-validate` on `jonaki.desktop` and `potplayer.desktop`.
- **MPRIS2 D-Bus**: Root and Player interfaces, media keys, track properties, playback status, position, and metadata dictionary verified.

### H. Security and Data Integrity (`TC-SEC-01` to `TC-SEC-05`, `TC-DB-01` to `TC-DB-09`)
- **Path Traversal**: Sanitization with `os.path.basename` prevents directory climbing in shaders and captures.
- **Subprocess Safety**: Capture routines execute argument lists without `shell=True`.
- **SQLite Database**: WAL mode, schema migrations, foreign keys, SQL injection resistance, and multi-threaded write transactions verified.
- **Defects Discovered**:
  - `DEF-SEC-01`: `enable_shader("")` accepts empty string, appending directory path.
  - `DEF-SEC-02`: Corrupted SQLite database crashes player on launch without recovery.
  - `DEF-SEC-03`: IPC socket file created with `0775` permissions instead of `0600`.
  - `DEF-SYS-01`: Root-level non-existent files misclassified as unrecognized switches (`/movie.mp4`).

---

## 3. Post-Fix Verification & Final Regression Run

**Execution Timestamp:** 2026-10-27 23:06:31 UTC+6  
**Runner:** Python Standard Library `unittest` discovery & ElementTree JUnit exporter  
**JUnit XML Artifact:** [`qa_reports/junit_report.xml`](file:///home/ashik/Data/Projects/PotPlayer/qa_reports/junit_report.xml)

### Summary Statistics

| Metric | Baseline (Pre-Fix) | Post-Fix Final Execution | Variance / Outcome |
| :--- | :---: | :---: | :---: |
| **Total Test Cases** | 271 | **271** | Expanded from 107 original tests |
| **Passed** | 269 | **271** | **+2 (+100% Pass Rate)** |
| **Failures** | 2 | **0** | **-2 (100% Resolved)** |
| **Errors** | 0 | **0** | **0** |
| **Skipped** | 0 | **0** | **0** |
| **Execution Duration** | 29.34s | **29.55s** | High-throughput, stable runtime |
| **Pass Percentage** | 99.26% | **100.00%** | **All Acceptance Criteria Met** |

### Per-Suite Final Results

| Suite Module | Cases | Result | Defect Regressions Verified |
| :--- | :---: | :---: | :--- |
| `tests/test_playback_integration.py` | 60 | **60 / 60 PASS** | `DEF-PLY-01`, `DEF-PLY-02`, `DEF-MED-01`, `DEF-MED-02`, `DEF-VID-01`, `DEF-VID-02`, `DEF-AUD-01` |
| `tests/test_ui_comprehensive.py` | 51 | **51 / 51 PASS** | `DEF-UI-01`, `DEF-UI-02`, `DEF-UI-03`, `DEF-UI-04` |
| `tests/test_systems_and_security.py` | 53 | **53 / 53 PASS** | `DEF-SYS-01`, `DEF-SEC-01`, `DEF-SEC-02`, `DEF-SEC-03`, `DEF-IPC-01`, `DEF-IPC-02` |
| `tests/test_engine.py` | 44 | **44 / 44 PASS** | `DEF-PLY-03`, EOF seek reset, timer tick robustness |
| `tests/test_cli.py` | 11 | **11 / 11 PASS** | Root file vs switch parsing |
| `tests/test_cursor_and_controls.py` | 4 | **4 / 4 PASS** | Cursor auto-hide timer & motion unhide |
| `tests/test_equalizer.py` | 8 | **8 / 8 PASS** | Graphic EQ DSP 10-band gain mathematical integrity |
| `tests/test_ipc.py` | 6 | **6 / 6 PASS** | Multi-instance locking & socket permission mask |
| `tests/test_media_db.py` | 7 | **7 / 7 PASS** | SQLite recovery from file corruption |
| `tests/test_playlist_view.py` | 6 | **6 / 6 PASS** | Playlist item bounds & bracket search escaping |
| `tests/test_skin_engine.py` | 7 | **7 / 7 PASS** | DSF bottom bar button hit-testing & full-screen button |
| `tests/test_subtitle_and_mpris.py` | 6 | **6 / 6 PASS** | MPRIS2 D-Bus properties & subtitle track cycling |
| `tests/test_audit_fixes.py` | 4 | **4 / 4 PASS** | Engine fix regressions |
| `tests/test_ui_audit_fixes.py` | 4 | **4 / 4 PASS** | Control box, preamp, and shader regressions |
| **Total** | **271** | **271 PASS (100%)** | **0 Failures, 0 Errors, 0 Blocked** |
