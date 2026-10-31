# JONAKI PLAYER — AUDIT FINDINGS VERIFICATION REPORT
**Role:** Senior Linux Desktop Application Engineer  
**Project:** Jonaki Player  
**Audit Source:** `07_GEMINI_IMPLEMENTATION_BACKLOG.md` & `02_TECHNICAL_FINDINGS.md`  
**Date:** October 2026  
**Status:** ALL FINDINGS INDEPENDENTLY VERIFIED  

---

## 1. Verification Summary Table

| Finding ID | Task ID | Subsystem | Severity | Code Location | Verified Root Cause | Finding Status |
|:---|:---:|:---|:---:|:---|:---|:---:|
| **FINDING-01** | `TASK-01` | Core Engine | **P0** | `src/core/engine.py:234-250` | `JonakiCore.handle` destroyed by `stop_engine()` without locking while worker threads invoke FFI calls. | **VERIFIED** |
| **FINDING-04** | `TASK-02` | Packaging | **P1** | `lib/libmpv.so.2.5.0`, `src/gi/` | Foreign Debian 13/Python 3.13 `.so` files hardcoded to Debian ABIs break Ubuntu/Fedora. | **VERIFIED** |
| **FINDING-02** | `TASK-03` | Core Engine | **P1** | `src/core/engine.py:228-232` | Missing `mpv_set_wakeup_callback`/`mpv_wait_event`; 10 Hz polling loop wastes power; ringbuffer drops. | **VERIFIED** |
| **FINDING-05** | `TASK-04` | Core Engine | **P1** | `src/core/engine.py:492-501` | `seek` commands omit `+exact`, snapping to keyframes. Previous QA fix was a false pass. | **VERIFIED** |
| **FINDING-06** | `TASK-05` | Torrent | **P1 / SEC** | `src/torrent/engine.py:334-336` | `get_selected_file_path()` performs `os.path.join(save_path, rel_path)` without `commonpath` check. | **VERIFIED** |
| **FINDING-09** | `TASK-06` | IPC Server | **P2 / SEC** | `src/core/ipc.py:152-156` | `_release_lock()` unlinks flock file, breaking POSIX advisory lock synchronization. Unbounded threads. | **VERIFIED** |
| **FINDING-07** | `TASK-07` | Playlist | **P2** | `src/ui/playlist_view.py:117-123` | Reorder maps items by `item["path"]`, collapsing duplicate tracks and corrupting playlists. | **VERIFIED** |
| **FINDING-08** | `TASK-08` | Audio DSP | **P2** | `src/core/engine.py:526` | `JonakiCore.set_equalizer_band()` clamps to -12 dB whereas `EqualizerModel` allows -24 dB. | **VERIFIED** |
| **FINDING-11** | `TASK-09` | UI / Skin | **P2** | `src/ui/skin_engine.py:80-270` | No HiDPI scale factor querying; hardcoded 96 DPI pixel coordinates cause microscopic UI on 4K. | **VERIFIED** |
| **FINDING-10** | `TASK-10` | Subtitles | **P2** | `src/subtitle/online_search.py:61` | Queries deprecated `rest.opensubtitles.org` endpoint without modern API v1/v2 credentials. | **VERIFIED** |
| **FINDING-03** | `TASK-11` | Desktop/Wayland | **P2 / DOC** | `bin/jonaki`, `src/jonaki.py` | Launcher unsets `WAYLAND_DISPLAY` and forces `GDK_BACKEND=x11`, contradicting "Native Wayland" docs. | **VERIFIED** |
| **FINDING-12** | `TASK-12` | Documentation | **P3 / DOC** | `README.md`, `MEMORY.md` | Advertises "zero-copy rendering", "8K 60fps", and 31 GLSL shaders which do not exist in Linux engine. | **VERIFIED** |
| **FINDING-13** | `TASK-12` | Video Shaders | **P3 / DOC** | `docs/PIXEL_SHADERS_AND_VAPOURSYNTH.md` | Documents Windows reverse-engineered VapourSynth scripts as functional Linux features. | **VERIFIED** |
| **GAP-01** | `TASK-13` | CI / Testing | **P2 / QA** | `.github/` (Missing) | No GitHub Actions workflow exists; tests run headless with `vo=null`, masking video surface failures. | **VERIFIED** |
| **GAP-02** | `TASK-14` | Test Isolation | **P2 / QA** | `tests/test_playback_core.py` | Over-reliance on synthetic mocks for C-FFI calls; lacks real libmpv integration test suite. | **VERIFIED** |

---

## 2. In-Depth Subsystem Findings Analysis

### 2.1 Core Engine Safety (`FINDING-01`, `FINDING-02`, `FINDING-05`)
- **Inspection:** Inspected `src/core/engine.py`.
- **Finding 01:** `JonakiCore` contains no reentrant lock or handle state validation during FFI calls. `stop_engine()` sets `self.handle = None` and calls `mpv_terminate_destroy(h)`. Concurrently running MPRIS2 or IPC threads querying properties can dereference a null pointer or execute FFI functions against a destroyed handle.
- **Finding 02:** Libmpv provides `mpv_set_wakeup_callback` to notify the host application when events arrive. The current engine never registers this callback. Instead, it relies entirely on `GLib.timeout_add(100, self._query_time_tick)`, which runs a 10 Hz polling loop and leaves the internal 1000-event queue unprocessed.
- **Finding 05:** `seek_relative()` and `seek_absolute()` execute `seek <val> relative` and `seek <val> absolute`. In libmpv, these snap to keyframes. `+exact` must be appended (`seek <val> relative+exact`) to achieve sample-accurate seeking.

### 2.2 Packaging & Binary Distribution (`FINDING-04`)
- **Inspection:** Inspected `lib/` and `src/gi/`.
- **Finding 04:** `lib/libmpv.so.2.5.0` is an ELF 64-bit LSB shared object compiled on Debian 13 (Trixie). `src/gi/_gi_cairo.cpython-313-x86_64-linux-gnu.so` is a Python 3.13 C-extension. Running on Ubuntu 24.04 (Python 3.12) or Fedora 40 fails immediately with symbol loading and ABI mismatch errors. System `libmpv.so.2` is readily discoverable via `ctypes.util.find_library('mpv')`.

### 2.3 BitTorrent Security (`FINDING-06`)
- **Inspection:** Inspected `src/torrent/engine.py:334-336`.
- **Finding 06:** `get_selected_file_path()` computes `os.path.join(save_path, rel_path)`. If `rel_path` from torrent metadata contains `../` sequences or leading slashes, it escapes the designated download directory.

### 2.4 IPC and Advisory Locks (`FINDING-09`)
- **Inspection:** Inspected `src/core/ipc.py:152-156`.
- **Finding 09:** `_release_lock()` unlinks `self.lock_path`. In Linux, unlinking an open advisory lock breaks `flock` mutual exclusion for concurrent waiting processes. Moreover, `_listen_loop()` spawns an unbounded thread per incoming socket connection.

### 2.5 Playlist & Audio DSP (`FINDING-07`, `FINDING-08`)
- **Inspection:** Inspected `src/ui/playlist_view.py:117-123` and `src/core/engine.py:526`.
- **Finding 07:** `path_map = {item["path"]: item for item in self.player.playlist}` collapses multiple playlist rows that reference the same file into a single entry, corrupting the playlist during drag-and-drop reordering.
- **Finding 08:** `set_equalizer_band()` clamps gain between `-12.0` and `+12.0` dB, whereas the UI model `EqualizerModel` supports cuts down to `-24.0` dB.

### 2.6 UI, Wayland, and External APIs (`FINDING-10`, `FINDING-11`, `FINDING-03`)
- **Inspection:** Inspected `src/ui/skin_engine.py`, `bin/jonaki`, `src/jonaki.py`, `src/subtitle/online_search.py`.
- **Finding 10:** Legacy OpenSubtitles REST endpoint is deprecated and returns HTTP errors.
- **Finding 11:** `SkinEngine` does not inspect `window.get_scale_factor()`, rendering 96 DPI assets at 1:1 pixel ratios on 4K HiDPI screens.
- **Finding 03:** Launchers force X11 mode by unsetting `WAYLAND_DISPLAY` and setting `GDK_BACKEND=x11`, while documentation advertises native Wayland.
