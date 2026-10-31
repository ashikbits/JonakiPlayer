# JONAKI PLAYER — MILESTONE 1 COMPLETION REPORT
**Milestone:** Milestone 1 — Core Engine Safety & Portability  
**Role:** Senior Linux Desktop Application Engineer  
**Date:** October 2026  
**Status:** ALL MILESTONE 1 TASKS VERIFIED AND PASSED  

---

## 1. Executive Summary

Milestone 1 addresses the highest-risk architectural defects in the core playback engine and binary distribution. All four targeted tasks have been implemented, verified, and backed by automated regression tests:
- **TASK-01:** Reentrant mutex synchronization (`threading.RLock`) added to `JonakiCore`. Handle lifecycle during `stop_engine()` is strictly synchronized to prevent Use-After-Free crashes during shutdown.
- **TASK-02:** Bundled foreign `.so` files (`lib/libmpv.so.2.5.0`, `src/gi/_gi_cairo...so`, `lib/gstreamer-1.0`) removed from Git. Portable dynamic library discovery implemented via `ctypes.util.find_library('mpv')` and standard system sonames. `install.sh` updated with distro packaging requirements.
- **TASK-03:** `mpv_set_wakeup_callback` and `mpv_wait_event` declared in C-FFI. Libmpv event draining integrated with GLib main loop via `GLib.idle_add()`.
- **TASK-04:** Exact seek enforcement using `relative+exact`, `absolute+exact`, and `absolute-percent+exact` flags.

---

## 2. Task Completion Details

### TASK-01: Thread Synchronization and libmpv Handle Lifecycle Safety
- **Status:** `VERIFIED FIX`
- **Original Finding:** `FINDING-01 (P0)`
- **Files Modified:** `src/core/engine.py`
- **Implementation:**
  - Added reentrant lock `self._lock = threading.RLock()` and run flag `self._is_running`.
  - Guarded all C-FFI invocations (`command`, `command_args`, `set_property`, `get_property`, `set_wid`, `_drain_mpv_events`) with `with self._lock:` and explicit null checks against `self.handle`.
  - Refactored `stop_engine()` to atomically set `self._is_running = False` and `self.handle = None` under the lock, followed by safe handle destruction (`mpv_terminate_destroy(h)`) outside the lock boundary to eliminate teardown deadlocks.
- **Verification:**
  - Added `test_thread_safety_concurrency_during_teardown` in `tests/test_milestone_1_engine_safety.py`. 10 threads bombarded `JonakiCore` with simultaneous property queries and commands during rapid teardown without a single `SIGSEGV` or exception.

---

### TASK-02: Remove Bundled Binaries & Implement System libmpv Discovery
- **Status:** `VERIFIED FIX`
- **Original Finding:** `FINDING-04 (P1)`, `FINDING-14 (LEGAL)`
- **Files Removed/Modified:**
  - Removed `lib/libmpv.so.2.5.0`, `lib/libmpv.so.2`, `lib/libmpv.so`, `src/gi/_gi_cairo.cpython-313-x86_64-linux-gnu.so`, `lib/gstreamer-1.0`.
  - Modified `src/core/engine.py` (replaced `_load_bundled_libmpv` with `_load_libmpv`).
  - Modified `install.sh` (added system libmpv dependency check and package names for Debian/Ubuntu, Fedora, Arch).
- **Implementation:**
  - Dynamically searches for `libmpv` using `ctypes.util.find_library("mpv")`, followed by standard Linux sonames (`libmpv.so.2`, `libmpv.so.1`, `libmpv.so`) in `/usr/lib`, `/usr/lib64`, and `/usr/local/lib`.
  - Clear user-facing `RuntimeError` providing exact distro install commands if libmpv is missing.
- **Verification:**
  - Automated test `test_dynamic_libmpv_discovery` in `tests/test_milestone_1_engine_safety.py` passed against system `libmpv.so.2`.

---

### TASK-03: Native libmpv Wakeup Callback and Event-Loop Integration
- **Status:** `VERIFIED FIX`
- **Original Finding:** `FINDING-02 (P1)`
- **Files Modified:** `src/core/engine.py`
- **Implementation:**
  - Added C ctypes prototypes for `mpv_set_wakeup_callback`, `mpv_wait_event`, and `struct mpv_event`.
  - Registered wakeup callback `_on_mpv_wakeup` with retained `CFUNCTYPE` instance reference to prevent garbage collection.
  - Callback schedules `_drain_mpv_events` onto the GTK main loop via `GLib.idle_add()`.
  - `_drain_mpv_events` non-blockingly drains events with `timeout=0.0` until `MPV_EVENT_NONE`, dispatching events directly to `_handle_mpv_event`.
- **Verification:**
  - Tested in `test_wakeup_callback_and_event_drain` and full playback integration suite (61 tests in `test_playback_integration.py`).

---

### TASK-04: Exact Seeking Enforcement (+exact)
- **Status:** `VERIFIED FIX`
- **Original Finding:** `FINDING-05 (P1)`
- **Files Modified:** `src/core/engine.py`, `tests/test_engine.py`
- **Implementation:**
  - Updated `seek_relative(delta, exact=True)` to use `relative+exact` (or `relative+keyframes` when `exact=False`).
  - Updated `seek_absolute(pos, exact=True)` to use `absolute+exact` (or `absolute+keyframes` when `exact=False`).
  - Updated `seek_percent(pct, exact=True)` to use `absolute-percent+exact` (or `absolute-percent+keyframes` when `exact=False`).
  - Updated regression test assertions in `tests/test_engine.py` to assert the verified exact commands.
- **Verification:**
  - Unit test `test_exact_seek_enforcement` verified all combinations of exact and keyframe seeks.

---

## 3. Milestone 1 Test Summary

| Test Suite | Tests Run | Result | Duration |
|:---|:---:|:---:|:---:|
| `tests/test_milestone_1_engine_safety.py` | 4 | **PASS** | 0.136s |
| `tests/test_engine.py` | 26 | **PASS** | 0.410s |
| `tests/test_playback_integration.py` | 61 | **PASS** | 18.460s |

**Total:** 91 tests passed with 0 failures and 0 errors.
