# Jonaki Player — SQA Confirmed Defect Log

**Date:** 2026-10-27  
**Auditor:** Senior Software QA Engineer & Linux Desktop Application Tester  
**Repository:** `ashik60/JonakiPlayer` (`/home/ashik/Data/Projects/Jonaki`)  
**Commit:** `9743287`  
**Test Environment:** Debian GNU/Linux 13 (Trixie), Kernel 6.12.113+deb13-amd64, x86_64, DISPLAY=:1  

---

## Defect Summary Matrix

| Defect ID | Severity | Priority | Component | Concise Description | Status |
| :--- | :---: | :---: | :--- | :--- | :---: |
| **DEF-PLY-01** | High | P1 | `src/core/engine.py` | Replay blocked by infinite STOPPED recursion at EOF | **Resolved & Verified** |
| **DEF-MED-01** | High | P1 | `src/core/engine.py` | Core state remains stuck in `PLAYING` on corrupted or empty files | **Resolved & Verified** |
| **DEF-SEC-02** | Medium | P1 | `src/core/media_db.py` | Corrupted SQLite database crashes application on startup | **Resolved & Verified** |
| **DEF-SYS-01** | Medium | P2 | `src/jonaki.py` | Non-existent root-level file paths misclassified as unrecognized switches | **Resolved & Verified** |
| **DEF-SEC-01** | Medium | P2 | `src/video/shader_manager.py` | `enable_shader("")` accepts empty string, appending directory path | **Resolved & Verified** |
| **DEF-IPC-01** | Medium | P2 | `src/core/ipc.py` | IPC server backlog of 10 drops connections during burst concurrency | **Resolved & Verified** |
| **DEF-PLY-02** | Medium | P2 | `src/core/engine.py` | Seek commands without `+exact` snap to keyframes causing backwards jumps | **Resolved & Verified** |
| **DEF-PLY-03** | Medium | P2 | `src/core/engine.py` | `play()` and `play_pause()` transition state to `PLAYING` without file loaded | **Resolved & Verified** |
| **DEF-MED-02** | Medium | P2 | `src/core/engine.py` | `load_file()` silently queues into `_pending_file` when `wid` is None | **Resolved & Verified** |
| **DEF-UI-01** | Medium | P2 | `src/ui/skin_engine.py` | Fullscreen toggle button missing from bottom DSF skin control bar | **Resolved & Verified** |
| **DEF-SEC-03** | Low | P3 | `src/core/ipc.py` | Unix domain IPC socket file permissions inherit default umask (`0775`) | **Resolved & Verified** |
| **DEF-IPC-02** | Low | P3 | `src/core/ipc.py` | Zero-length IPC payload causes silent disconnect instead of JSON error | **Resolved & Verified** |
| **DEF-UI-02** | Low | P3 | `src/ui/control_box.py` | Denoise hook omitted from Control Box Shaders tab | **Resolved & Verified** |
| **DEF-UI-03** | Low | P3 | `src/ui/main_window.py` | PreAmp boost ceiling mismatch (+12 dB via shortcut vs +24 dB via menu) | **Resolved & Verified** |
| **DEF-UI-04** | Low | P3 | `src/ui/media_info_dialog.py` | GTK 3 deprecation warning on `Gtk.Widget.override_font` | **Resolved & Verified** |
| **DEF-VID-01** | Low | P3 | `src/core/engine.py` | Phantom audio/video metadata in `get_media_detailed_info()` | **Resolved & Verified** |
| **DEF-VID-02** | Low | P3 | `src/core/engine.py` | `set_video_colors()` clobbers unspecified color parameters to 0.0 | **Resolved & Verified** |
| **DEF-AUD-01** | Low | P3 | `src/core/engine.py` | Duplicate `get_property("pause")` query in `_query_time_tick()` | **Resolved & Verified** |

---

## Detailed Defect Reports

### DEF-PLY-01: Replay Blocked by Infinite STOPPED Recursion at EOF
- **Severity:** High | **Priority:** P1
- **Component:** `src/core/engine.py` (`JonakiCore._query_time_tick`, `play`, `play_pause`)
- **Environment:** Debian 13 x86_64, in-process `libmpv` 0.40.0
- **Preconditions:** A media file is loaded and played to completion (`eof-reached == "yes"`, `keep-open=yes`).
- **Reproduction Steps:**
  1. Load and play any video file until it reaches end-of-file.
  2. The engine transitions to `state = STOPPED`.
  3. Call `core.play()` or press Space to replay the file.
- **Expected Behavior:** The engine seeks back to timestamp `00:00:00` and resumes playback from the start.
- **Actual Behavior:** `core.play()` sets `state = PLAYING`. Within 100ms, `_query_time_tick()` reads `eof-reached == "yes"`. Because `state == PLAYING`, it immediately resets `state = STOPPED` and calls `on_file_end()`. The file cannot be replayed.
- **Reproduction Frequency:** 100% (deterministic).
- **Root Cause:** In `engine.py:301-310`, `_query_time_tick` does not clear EOF state or check position before re-asserting `PlaybackState.STOPPED`.
- **Recommended Fix:** In `play()` and `play_pause()`, check if `get_property("eof-reached") == "yes"` or `(self.duration > 0 and self.position >= self.duration - 0.2)`. If so, call `self.seek_absolute(0.0)` before resuming.
- **Regression Test:** `tests/test_playback_integration.py:TC-PLY-15`.

---

### DEF-MED-01: Core State Remains Stuck in `PLAYING` on Corrupted or Empty Files
- **Severity:** High | **Priority:** P1
- **Component:** `src/core/engine.py` (`JonakiCore.load_file`, `_query_time_tick`)
- **Environment:** Debian 13 x86_64
- **Preconditions:** Engine initialized.
- **Reproduction Steps:**
  1. Call `core.load_file("empty_file.mp4")` or `core.load_file("corrupted_header.mp4")`.
  2. Wait 500ms for demuxing failure.
  3. Inspect `core.state`.
- **Expected Behavior:** Demuxing failure detects `playback-abort == "yes"`, transitioning engine to `PlaybackState.STOPPED` and clearing `current_file`.
- **Actual Behavior:** `_load_file_internal` sets `state = PLAYING`. When libmpv aborts demuxing, `_query_time_tick()` only checks `eof-reached` and `pause`. Neither is set, leaving `state` permanently stuck in `PLAYING` with `00:00:00` position.
- **Reproduction Frequency:** 100% (deterministic).
- **Root Cause:** In `engine.py:288-337`, `_query_time_tick()` fails to inspect `self.get_property("playback-abort")`.
- **Recommended Fix:** Check `self.get_property("playback-abort") == "yes"` in `_query_time_tick()`: transition `self.state = PlaybackState.STOPPED` and `self.current_file = None`.
- **Regression Test:** `tests/test_systems_and_security.py:TC-REL-07`, `tests/test_playback_integration.py:TC-MED-15`.

---

### DEF-SEC-02: Corrupted SQLite Database Crashes Application on Startup
- **Severity:** Medium | **Priority:** P1
- **Component:** `src/core/media_db.py` (`MediaDatabase.__init__`, `_init_database`)
- **Environment:** Debian 13 x86_64
- **Preconditions:** `~/.config/jonaki/mediadb.sqlite` contains corrupted headers or garbage data.
- **Reproduction Steps:**
  1. Corrupt the database file: `echo "INVALID_DATA" > ~/.config/jonaki/mediadb.sqlite`.
  2. Launch Jonaki Player: `jonaki`.
- **Expected Behavior:** The application detects the corrupted database, quarantines it as `mediadb.sqlite.corrupt.<timestamp>`, initializes a clean database, and launches normally.
- **Actual Behavior:** Unhandled `sqlite3.DatabaseError: file is not a database` crashes the application during initialization of `JonakiMainWindow`.
- **Reproduction Frequency:** 100% (deterministic).
- **Root Cause:** `_init_database()` executes `PRAGMA journal_mode = WAL;` without catching `sqlite3.DatabaseError`.
- **Recommended Fix:** In `MediaDatabase.__init__`, catch `sqlite3.DatabaseError`, quarantine the corrupted file, and recreate the schema.
- **Regression Test:** `tests/test_systems_and_security.py:TC-DB-08`.

---

### DEF-SYS-01: Non-Existent Root Files Misidentified as Unrecognized Switches
- **Severity:** Medium | **Priority:** P2
- **Component:** `src/jonaki.py:208` (`parse_arguments`)
- **Environment:** Debian 13 x86_64
- **Preconditions:** Player invoked from command line with a non-existent absolute file path in root directory.
- **Reproduction Steps:**
  1. Execute `jonaki /movie.mp4` (where `/movie.mp4` does not exist on disk).
- **Expected Behavior:** Argument `/movie.mp4` is treated as a target file path and added to `options["contents"]`.
- **Actual Behavior:** Warning is printed: `[Jonaki] Warning: Unrecognized switch '/movie.mp4'` and the file is dropped from `options["contents"]`.
- **Reproduction Frequency:** 100% (deterministic).
- **Root Cause:** Line 208 evaluates `elif clean.startswith("/") and ("/" not in clean[1:] or "=" in clean):`. Because `clean[1:]` contains no second slash, it is assumed to be a switch.
- **Recommended Fix:** Distinguish switch names from file paths by testing known switch prefixes or file extensions (`.mp4`, `.mkv`, `.webm`, etc.).
- **Regression Test:** `tests/test_systems_and_security.py:TC-SYS-08`.

---

### DEF-SEC-01: VideoShaderManager Accepts Empty String, Appending Directory Path
- **Severity:** Medium | **Priority:** P2
- **Component:** `src/video/shader_manager.py:35-41` (`enable_shader`)
- **Environment:** Debian 13 x86_64
- **Preconditions:** `VideoShaderManager` instantiated.
- **Reproduction Steps:**
  1. Call `shader_mgr.enable_shader("")`.
- **Expected Behavior:** Empty string input is rejected, returning `False`.
- **Actual Behavior:** Returns `True` and appends `.../assets/shaders/` directory to `active_shaders` and passes directory path to mpv's `glsl-shaders`.
- **Reproduction Frequency:** 100% (deterministic).
- **Root Cause:** `os.path.basename("") == ""` and `os.path.join(shaders_dir, "") == shaders_dir`. Since `os.path.exists(shaders_dir)` is `True`, it is accepted.
- **Recommended Fix:** Guard with `if not shader_filename or not shader_filename.strip(): return False` and ensure `os.path.isfile(target_path)`.
- **Regression Test:** `tests/test_systems_and_security.py:TC-SEC-02`.

---

### DEF-IPC-01: IPC Server Backlog of 10 Causes Connection Drops During Concurrency Bursts
- **Severity:** Medium | **Priority:** P2
- **Component:** `src/core/ipc.py:117` (`IPCServer.start`), `IPCClient.send_command`
- **Environment:** Linux x86_64
- **Preconditions:** Primary Jonaki instance is running.
- **Reproduction Steps:**
  1. Dispatch 25 concurrent client connections (e.g. file manager queuing multiple files).
- **Expected Behavior:** All 25 connections are accepted and queued into the playlist.
- **Actual Behavior:** 3-5 connections are dropped with `[Errno 11] Resource temporarily unavailable`.
- **Reproduction Frequency:** Frequent under burst concurrency.
- **Root Cause:** `self._server_socket.listen(10)` backlog is saturated by kernel before worker threads call `accept()`.
- **Recommended Fix:** Increase listen backlog to `self._server_socket.listen(128)` and add brief retry loop in `IPCClient.send_command`.
- **Regression Test:** `tests/test_systems_and_security.py:TC-IPC-11`.

---

### DEF-PLY-02: Seek Commands Without `+exact` Snap to Keyframes
- **Severity:** Medium | **Priority:** P2
- **Component:** `src/core/engine.py:450, 456` (`seek_relative`, `seek_percent`)
- **Environment:** Linux x86_64
- **Preconditions:** Media file with sparse keyframes (e.g. 5-10 second GOP) loaded.
- **Reproduction Steps:**
  1. Play file at timestamp 0.0s.
  2. Call `seek_relative(1.0)` or seek timeline slider slightly.
- **Expected Behavior:** Player jumps accurately to timestamp 1.0s.
- **Actual Behavior:** Player snaps backwards to 0.0s because keyframe seeking rounds down to the preceding keyframe.
- **Reproduction Frequency:** 100% on media with sparse keyframes.
- **Root Cause:** mpv commands `seek <delta> relative` and `seek <p> absolute-percent` use keyframe seeking by default.
- **Recommended Fix:** Change commands to `seek <delta> relative+exact` and `seek <p> absolute-percent+exact`.
- **Regression Test:** `tests/test_playback_integration.py:TC-PLY-03`.

---

### DEF-PLY-03: `play()` and `play_pause()` Transition State Without File Loaded
- **Severity:** Medium | **Priority:** P2
- **Component:** `src/core/engine.py:417-434` (`play`, `play_pause`)
- **Environment:** Linux x86_64
- **Preconditions:** Engine initialized, `current_file == None`.
- **Reproduction Steps:**
  1. Call `core.play()` or `core.play_pause()`.
- **Expected Behavior:** Command is ignored; engine stays in `PlaybackState.IDLE`.
- **Actual Behavior:** Engine transitions to `PlaybackState.PLAYING` and emits 10Hz `on_time_update(0.0, 0.0)` events despite no media loaded.
- **Reproduction Frequency:** 100% (deterministic).
- **Root Cause:** Missing guard `if not self.current_file: return` in `play()` and `play_pause()`.
- **Recommended Fix:** Add guard `if not self.current_file: return`.
- **Regression Test:** `tests/test_playback_integration.py:TC-PLY-08`.

---

### DEF-MED-02: `load_file()` Silently Queues When `wid` Is None
- **Severity:** Medium | **Priority:** P2
- **Component:** `src/core/engine.py:370-372` (`load_file`)
- **Environment:** Linux x86_64 (Headless / Audio-only / CLI mode)
- **Preconditions:** `JonakiCore` initialized without GUI `wid` (e.g. `wid=None`, `vo=null`).
- **Reproduction Steps:**
  1. Instantiate `core = JonakiCore(wid=None)`.
  2. Call `core.load_file("audio_only.mp3")`.
- **Expected Behavior:** Media loads and plays via null video output.
- **Actual Behavior:** `if not self.wid: self._pending_file = ...; return` stores file in `_pending_file` and never plays.
- **Reproduction Frequency:** 100% when `wid` is None.
- **Root Cause:** GUI window ID realization logic is hardcoded into `load_file()`.
- **Recommended Fix:** Check `if not self.wid and self.get_property("vo") != "null": self._pending_file = ...; return`.
- **Regression Test:** `tests/test_playback_integration.py:TC-MED-06`.

---

### DEF-UI-01: Fullscreen Button Missing from Bottom DSF Skin Control Bar
- **Severity:** Medium | **Priority:** P2
- **Component:** `src/ui/skin_engine.py:157-168`, `layout()`, `render()`
- **Environment:** Linux Desktop
- **Preconditions:** Jonaki Player main window open.
- **Reproduction Steps:**
  1. Inspect the right tool section of the bottom skin bar.
- **Expected Behavior:** A fullscreen toggle button (`CMD_FULLSCREEN`) is present alongside Stream, Playlist, and Control Box buttons.
- **Actual Behavior:** Fullscreen button is absent from skin buttons. Users cannot click to fullscreen.
- **Reproduction Frequency:** 100% (UI omission).
- **Root Cause:** `PotSkinEngine._init_default_controls` does not instantiate `btn_fullscreen`.
- **Recommended Fix:** Add `btn_fullscreen` to `_init_default_controls`, `layout()`, and `render()`.
- **Regression Test:** `tests/test_ui_comprehensive.py:TC-SKIN-09`.

---

### DEF-SEC-03: Unix Domain IPC Socket Permissions Inherit Default Umask
- **Severity:** Low | **Priority:** P3
- **Component:** `src/core/ipc.py:115` (`IPCServer.start`)
- **Environment:** Linux x86_64
- **Preconditions:** Jonaki Player launched.
- **Reproduction Steps:**
  1. Inspect permissions of `$XDG_RUNTIME_DIR/jonaki_ipc.sock`.
- **Expected Behavior:** Socket permissions are restricted to user-only (`0600`).
- **Actual Behavior:** Socket file is created with default umask (`0775` or `0755`), allowing other local users to connect if in shared directories.
- **Reproduction Frequency:** 100%.
- **Root Cause:** Socket file is not explicitly chmodded after `bind()`.
- **Recommended Fix:** Call `os.chmod(self.socket_path, 0o600)` immediately after `bind()`.
- **Regression Test:** `tests/test_systems_and_security.py:TC-IPC-10`.

---

### DEF-IPC-02: Zero-Length IPC Payload Causes Silent Disconnect
- **Severity:** Low | **Priority:** P3
- **Component:** `src/core/ipc.py:153-156` (`IPCServer._handle_client`)
- **Environment:** Linux x86_64
- **Preconditions:** IPC server running.
- **Reproduction Steps:**
  1. Connect client and send 0-byte payload (`b""`).
- **Expected Behavior:** Server returns structured JSON error `{"status": "error", "message": "Empty payload"}`.
- **Actual Behavior:** Server silently closes connection because `if not data: return` treats `b""` as EOF.
- **Reproduction Frequency:** 100%.
- **Root Cause:** `if not data:` does not differentiate `data is None` (EOF) from `data == b""`.
- **Recommended Fix:** Change check to `if data is None: return` and handle `len(data) == 0` with error response.
- **Regression Test:** `tests/test_systems_and_security.py:TC-IPC-07`.

---

### DEF-UI-02: Denoise Hook Missing from Control Box Shaders Tab
- **Severity:** Low | **Priority:** P3
- **Component:** `src/ui/control_box.py:314-315` (`_create_shaders_tab`)
- **Environment:** Linux Desktop
- **Preconditions:** Open Control Box dialog (`F6`) -> Shaders Tab.
- **Reproduction Steps:**
  1. Inspect available shader checkbuttons.
- **Expected Behavior:** Denoise (`denoise.hook`) is present alongside Sharpen and Adaptive Sharpen.
- **Actual Behavior:** Only `sharpen.hook` and `adaptive_sharpen.hook` are displayed.
- **Reproduction Frequency:** 100%.
- **Root Cause:** Hardcoded list in `_create_shaders_tab()` omitted `"denoise.hook"`.
- **Recommended Fix:** Add `"denoise.hook"` to list of shaders in `_create_shaders_tab()`.
- **Regression Test:** `tests/test_ui_comprehensive.py:TC-CBOX-03`.

---

### DEF-UI-03: PreAmp Maximum Boost Cap Mismatch
- **Severity:** Low | **Priority:** P3
- **Component:** `src/ui/main_window.py:590` vs `src/ui/main_window.py:1156`
- **Environment:** Linux Desktop
- **Preconditions:** Active audio playback.
- **Reproduction Steps:**
  1. Press Shift+Up repeatedly past +12 dB.
  2. Right click -> Audio -> Volume Boost PreAmp (+1 dB) past +12 dB.
- **Expected Behavior:** Consistent maximum boost ceiling across keyboard shortcut and context menu.
- **Actual Behavior:** Keyboard shortcut caps at +12 dB; context menu caps at +24 dB.
- **Reproduction Frequency:** 100%.
- **Root Cause:** Inconsistent clamp limits in `_on_key_press` (`min(12.0, ...)`) vs `handle_command` (`min(24.0, ...)`).
- **Recommended Fix:** Standardize shortcut clamp limit to +24 dB.
- **Regression Test:** `tests/test_ui_comprehensive.py:TC-KEY-07`.

---

### DEF-UI-04: GTK 3 Deprecation Warnings in `MediaInfoDialog` and `PotContextMenu`
- **Severity:** Low | **Priority:** P3
- **Component:** `src/ui/media_info_dialog.py:51`, `src/ui/context_menu.py:336`
- **Environment:** Python 3.13 / GTK 3.24
- **Preconditions:** Running unittests.
- **Reproduction Steps:**
  1. Run `python3 -m unittest discover tests`.
- **Expected Behavior:** Clean terminal output without deprecation warnings.
- **Actual Behavior:** Emits `DeprecationWarning: Gtk.Widget.override_font is deprecated` and `DeprecationWarning: Gtk.Menu.popup_for_device is deprecated`.
- **Reproduction Frequency:** 100%.
- **Root Cause:** Legacy GTK 3 methods used instead of CSS provider and modern popup methods.
- **Recommended Fix:** Use CSS provider for font styling and modern popup API.
- **Regression Test:** Clean unittest execution.

---

### DEF-VID-01: Phantom Audio/Video Metadata in `get_media_detailed_info()`
- **Severity:** Low | **Priority:** P3
- **Component:** `src/core/engine.py:719-722` (`get_media_detailed_info`)
- **Environment:** Linux x86_64
- **Preconditions:** Video-only or audio-only media loaded.
- **Reproduction Steps:**
  1. Load `video_only_hevc.mkv` and call `get_media_detailed_info()`.
- **Expected Behavior:** Audio channels and sample rate report `None` / `0` / `"None"`.
- **Actual Behavior:** Reports `audio_channels: "2.0 (Stereo)"` and `sample_rate: 48000`.
- **Reproduction Frequency:** 100%.
- **Root Cause:** Fallback defaults applied unconditionally without checking if audio tracks exist.
- **Recommended Fix:** Check `len(self.get_audio_tracks()) > 0` before populating audio metadata.
- **Regression Test:** `tests/test_playback_integration.py:TC-VID-17`.

---

### DEF-VID-02: `set_video_colors()` Clobbers Unspecified Color Parameters
- **Severity:** Low | **Priority:** P3
- **Component:** `src/core/engine.py:522-529` (`set_video_colors`)
- **Environment:** Linux x86_64
- **Preconditions:** Contrast set to 20.0.
- **Reproduction Steps:**
  1. Call `core.set_video_colors(brightness=10.0)`.
- **Expected Behavior:** Brightness is set to 10.0; contrast remains at 20.0.
- **Actual Behavior:** Contrast is clobbered back to 0.0.
- **Reproduction Frequency:** 100%.
- **Root Cause:** Default parameters in function signature are `0.0` instead of `None`.
- **Recommended Fix:** Default parameters to `None` and keep existing values when `None`.
- **Regression Test:** `tests/test_playback_integration.py:TC-VID-01`.

---

### DEF-AUD-01: Duplicate C-FFI Property Query in `_query_time_tick()`
- **Severity:** Low | **Priority:** P3
- **Component:** `src/core/engine.py:294, 313` (`_query_time_tick`)
- **Environment:** Linux x86_64
- **Preconditions:** Active playback.
- **Reproduction Steps:**
  1. Inspect `_query_time_tick()` source.
- **Expected Behavior:** `get_property("pause")` queried once per tick.
- **Actual Behavior:** `get_property("pause")` called twice in the same 100ms tick.
- **Reproduction Frequency:** 100%.
- **Root Cause:** Redundant call at line 294 before EOF check.
- **Recommended Fix:** Query `pause_val` once and reuse throughout function.
- **Regression Test:** `tests/test_playback_integration.py:TC-AUD-01`.
