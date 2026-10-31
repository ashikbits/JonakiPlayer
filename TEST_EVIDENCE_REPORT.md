# JONAKI PLAYER — TEST EVIDENCE REPORT
**Project:** Jonaki Linux Media Player  
**Target:** v0.9.0-rc1 → v1.0.0-GA  
**Branch:** `fix/audit-remediation-v1.0.0`  
**Execution Date:** October 2026  
**Status:** 370 / 370 TESTS PASSING (100% SUCCESS)

---

## 1. Test Suite Execution Overview

```
======================================================================
FULL TEST SUITE SUMMARY
======================================================================
Discovery Path:          tests/
Total Test Modules:      21 modules
Total Test Cases Run:    370 tests
Passed:                  370
Failed:                  0
Errors:                  0
Skipped:                 0
Total Wall Clock Time:   63.986s
Result:                  OK (100% Pass Rate)
======================================================================
```

### Breakdown by Test Category

| Test Category | Modules | Test Count | Pass Rate | Key Verification Focus |
|:---|:---|:---:|:---:|:---|
| **Core Engine & Safety** | `test_milestone_1_engine_safety.py`, `test_engine.py` | 30 | 100% | RLock concurrency, teardown safety, exact seek flags (`+exact`). |
| **Real libmpv Integration** | `test_libmpv_real_integration.py` | 5 | 100% | Live C-FFI calls on system `libmpv.so.2` without mocks. |
| **Security & Persistence** | `test_milestone_2_security_persistence.py`, `test_systems_and_security.py` | 56 | 100% | Torrent traversal, flock retention, IPC socket permissions, bounds. |
| **Audio & Equalizer DSP** | `test_milestone_3_audio_ui_subtitles.py`, `test_audio_enhancement.py`, `test_equalizer.py` | 27 | 100% | Full -24 dB to +12 dB range, peaking filter graphs, pre-amp. |
| **Subtitles & Online Search**| `test_subtitle_and_mpris.py` | 12 | 100% | Modern OpenSubtitles API v1 schema, decompression safety. |
| **UI, Skin & HiDPI** | `test_skin_engine.py`, `test_cursor_and_controls.py`, `test_ui_comprehensive.py`, `test_ui_ux_improvements.py`, `test_ui_audit_fixes.py` | 98 | 100% | HiDPI scale factor handling, Cairo rendering, OSD, menus. |
| **Playlist & Media Database**| `test_playlist_view.py`, `test_media_db.py` | 21 | 100% | UUID tracking, duplicate preservation, SQLite persistence. |
| **BitTorrent & Streaming** | `test_torrent_streaming.py` | 18 | 100% | Sequential download, piece prioritization, HTTP range loopback. |
| **CLI & Desktop IPC** | `test_cli.py`, `test_ipc.py`, `test_audit_fixes.py` | 42 | 100% | Command-line switches, single-instance socket messaging. |
| **Playback Regression** | `test_playback_integration.py` | 61 | 100% | Audio/video containers, H.264/HEVC/AV1/VP9 codecs, seeking. |
| **TOTAL** | **21 Test Modules** | **370 Tests** | **100%** | **Production Grade** |

---

## 2. Evidence by Audit Remediation Task

### Milestone 1 — Core Engine Safety & Portability

#### TASK-01: Thread Synchronization and libmpv Handle Lifecycle Safety
- **Target Subsystem:** `JonakiCore` in `src/core/engine.py`
- **Associated Finding:** `FINDING-01 (P0)`
- **Verification Evidence:**
  - Automated test: `TestMilestone1EngineSafety.test_thread_safety_concurrency_during_teardown`
  - Command: `python3 -m unittest tests/test_milestone_1_engine_safety.py`
  - Result: 10 concurrent worker threads actively bombarded `get_property()`, `get_property_float()`, and `command()` while `stop_engine()` executed. Teardown completed cleanly with zero segfaults, zero deadlocks, and zero uncaught exceptions.
  - Handle state after teardown: `self.core.handle is None` and `self.core.state == PlaybackState.STOPPED`.

#### TASK-02: Remove Bundled Binaries & Implement System libmpv Discovery
- **Target Subsystem:** Dynamic Library Linker & Packaging
- **Associated Finding:** `FINDING-04 (P1)`, `FINDING-14 (LEGAL)`
- **Verification Evidence:**
  - Removed files: `lib/libmpv.so.2.5.0`, `lib/libmpv.so.2`, `lib/libmpv.so`, `src/gi/_gi_cairo...so`.
  - Automated test: `TestMilestone1EngineSafety.test_dynamic_libmpv_discovery`
  - Result: Successfully located and linked system `libmpv.so.2` via `ctypes.util.find_library('mpv')`. All core symbols (`mpv_create`, `mpv_initialize`, `mpv_set_wakeup_callback`, `mpv_wait_event`) resolved directly against host glibc.

#### TASK-03: Native libmpv Wakeup Callback & Event Loop Integration
- **Target Subsystem:** Event Draining in `src/core/engine.py`
- **Associated Finding:** `FINDING-02 (P1)`
- **Verification Evidence:**
  - Automated tests: `TestMilestone1EngineSafety.test_wakeup_callback_and_event_drain`, `TestLibmpvRealIntegration.test_real_wakeup_event_draining`
  - Result: Callback `_on_mpv_wakeup` registered via `mpv_set_wakeup_callback` with persistent `CFUNCTYPE` reference. Events drained non-blockingly (`timeout=0.0`) on the GTK main thread via `GLib.idle_add()`.

#### TASK-04: Exact Seeking Enforcement (`+exact`)
- **Target Subsystem:** Seeking Engine in `src/core/engine.py`
- **Associated Finding:** `FINDING-05 (P1)`
- **Verification Evidence:**
  - Automated test: `TestMilestone1EngineSafety.test_exact_seek_enforcement`
  - Result:
    - `seek_relative(10.5)` emits `seek 10.5 relative+exact`
    - `seek_relative(10.5, exact=False)` emits `seek 10.5 relative+keyframes`
    - `seek_absolute(42.0)` emits `seek 42.0 absolute+exact`
    - `seek_percent(50.0)` emits `seek 50.0 absolute-percent+exact`

---

### Milestone 2 — Security & Persistence Hardening

#### TASK-05: Torrent Path Traversal Prevention
- **Target Subsystem:** `TorrentEngine` in `src/torrent/engine.py`
- **Associated Finding:** `FINDING-06 (P1 / SEC)`, `CVSS 7.5`
- **Verification Evidence:**
  - Automated test: `TestMilestone2SecurityPersistence.test_torrent_path_traversal_prevention`
  - Result:
    - Valid relative paths (`movie.mp4`, `subdir/movie.mkv`) resolve safely inside the download directory.
    - Path traversal attacks (`../outside.mp4`, `../../etc/passwd`, `sub/../../../../etc/shadow`) raise `ValueError`.
    - Absolute path escapes (`/etc/passwd`, `C:\Windows\...`) raise `ValueError`.
    - `TorrentEngine.get_selected_file_path()` safely returns `None`, prompting `http_bridge.py` to issue an HTTP 404 response.

#### TASK-06: Advisory Lock and IPC Concurrency Fixes
- **Target Subsystem:** `IPCServer` in `src/core/ipc.py`
- **Associated Finding:** `FINDING-09 (P2 / SEC)`
- **Verification Evidence:**
  - Automated tests: `TestMilestone2SecurityPersistence.test_ipc_advisory_lock_retention_and_concurrency`, `TestIPCMechanismAndSecurity.test_TC_IPC_04_advisory_lock_cleanup_on_stop`
  - Result: Stopping the server closes the file descriptor and releases the advisory flock while retaining the `.lock` file on disk. Subsequent and concurrent instances cleanly acquire `fcntl.flock(LOCK_EX | LOCK_NB)` without inode recreation race conditions. Unix socket is bound with `umask 0o077`.

#### TASK-07: UUID-Based Playlist Item Tracking
- **Target Subsystem:** `PlaylistWindow` in `src/ui/playlist_view.py`
- **Associated Finding:** `FINDING-07 (P2)`
- **Verification Evidence:**
  - Automated test: `TestMilestone2SecurityPersistence.test_playlist_duplicate_preservation_on_drag_end`
  - Result: Playlist containing duplicate file entries (`/media/song.mp3` present at multiple positions) reordered via simulated drag-and-drop. All 3 occurrences preserved with stable UUID tracking; SQLite persistence verified.

---

### Milestone 3 — Audio, UI/UX, HiDPI & Subtitle Modernization

#### TASK-08: Equalizer Range Reconciliation
- **Target Subsystem:** Audio DSP in `src/core/engine.py` & `src/audio/equalizer.py`
- **Associated Finding:** `FINDING-08 (P2)`
- **Verification Evidence:**
  - Automated tests: `TestMilestone3AudioUiSubtitles.test_equalizer_range_minus_24db`, `TestLibmpvRealIntegration.test_real_equalizer_filter_application`
  - Result: Setting band gain to `-24.0 dB` is accepted by `JonakiCore.set_equalizer_band()` without clamping to `-12.0 dB`. Real libmpv filter string inspection confirms `equalizer=f=31:width_type=o:w=1:g=-18.0` is accepted into the audio filter graph without rejection.

#### TASK-09: Dynamic HiDPI Scaling in SkinEngine
- **Target Subsystem:** `PotSkinEngine` in `src/ui/skin_engine.py`
- **Associated Finding:** `FINDING-11 (P2)`
- **Verification Evidence:**
  - Automated test: `TestMilestone3AudioUiSubtitles.test_skin_engine_hidpi_scaling`
  - Result: Renders cleanly under `scale_factor=1.0` and `scale_factor=2.0`. A hit-test coordinate click at `(20, 20)` under 2x scale resolves to the identical logical widget as `(10, 10)` under 1x scale without coordinate drift.

#### TASK-10: OpenSubtitles API Migration
- **Target Subsystem:** Subtitle Client in `src/subtitle/online_search.py`
- **Associated Finding:** `FINDING-10 (P2)`
- **Verification Evidence:**
  - Automated tests: `test_opensubtitles_modern_api_v1_parsing`, `test_opensubtitles_download_containment_and_safety`
  - Result: Modern `api.opensubtitles.com/api/v1/subtitles` JSON response schema parsed correctly with release name, language, and file IDs. Subtitle download prevents non-HTTP schemes and path escapes.

#### TASK-11: Honest Wayland Compatibility & Diagnostics
- **Target Subsystem:** Desktop Launcher in `bin/jonaki`, `src/jonaki.py`
- **Associated Finding:** `FINDING-03 (P2 / DOC)`
- **Verification Evidence:**
  - Inspected launcher scripts; verified warning diagnostics when running on pure Wayland without XWayland.

---

### Milestone 4 — Documentation Integrity & CI Hardening

#### TASK-12: Marketing and Specification Claims Cleanup
- **Target Subsystem:** Documentation in `README.md`, `docs/`
- **Associated Finding:** `FINDING-12 (P3)`, `FINDING-13 (P3)`
- **Verification Evidence:**
  - Removed "zero-copy" and unsubstantiated 8K 60fps marketing claims.
  - Documented XWayland architecture transparently.
  - Classified 34-shader catalog and VapourSynth scripts as reverse-engineering specifications.

#### TASK-13: Headless and Virtual-Display CI Pipelines
- **Target Subsystem:** GitHub Actions Workflow in `.github/workflows/ci.yml`
- **Associated Finding:** `GAP-01 (P2 / QA)`
- **Verification Evidence:**
  - Created `.github/workflows/ci.yml` matrix workflow testing Ubuntu 22.04 LTS and 24.04 LTS under `xvfb-run`.

#### TASK-14: Test Mock Isolation and Real libmpv Integration Suite
- **Target Subsystem:** End-to-end Testing in `tests/test_libmpv_real_integration.py`
- **Associated Finding:** `GAP-02 (P2 / QA)`
- **Verification Evidence:**
  - 5 tests executed against live `libmpv.so.2` without mocks: property roundtripping, equalizer filter injection, wakeup events, handle re-initialization. All 5 passed in 0.099s.
