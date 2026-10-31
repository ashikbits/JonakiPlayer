# JONAKI PLAYER — MILESTONE 2 COMPLETION REPORT
**Milestone:** Milestone 2 — Security & Persistence Hardening  
**Role:** Senior Linux Desktop Application Engineer  
**Date:** October 2026  
**Status:** ALL MILESTONE 2 TASKS VERIFIED AND PASSED  

---

## 1. Executive Summary

Milestone 2 hardens Jonaki Player's security posture, IPC advisory locking, and playlist persistence:
- **TASK-05 (BitTorrent Path Traversal Defense):** Implemented `sanitize_torrent_path()` with strict validation rejecting leading slashes, backslashes, drive letters, and relative escapes (`../`). Validated against `os.path.commonpath`.
- **TASK-06 (Advisory Lock Retention & IPC Concurrency):** Corrected `IPCServer._release_lock()` to cease deleting the advisory `.lock` file from disk, ensuring POSIX `flock` mutual exclusion across concurrent and subsequent processes. Added a `threading.BoundedSemaphore(10)` to cap concurrent socket workers.
- **TASK-07 (UUID-Based Playlist Item Tracking):** Added unique UUID tracking per playlist entry and a hidden column in `Gtk.ListStore`. Drag-and-drop reordering now resolves entries by UUID instead of file path, preserving duplicate track entries and their exact reordered sequence.

---

## 2. Task Completion Details

### TASK-05: Torrent Path Traversal Prevention
- **Status:** `VERIFIED FIX`
- **Original Finding:** `FINDING-06 (P1 / SEC)`, `CVSS 7.5`
- **Files Modified:** `src/torrent/engine.py`
- **Implementation:**
  - Implemented `sanitize_torrent_path(base_dir, untrusted_rel_path)` which validates that target paths are strictly contained within `base_dir` using `os.path.commonpath([base_abs, target_abs]) == base_abs`.
  - Rejects absolute paths (`/etc/passwd`), drive escapes (`C:\...`), and directory traversal sequences (`../../etc/shadow`).
  - Integrated into `TorrentEngine.get_selected_file_path()`, returning `None` if an unsafe path is detected, which signals `http_bridge.py` to respond with HTTP 404 instead of opening arbitrary filesystem paths.
- **Verification:**
  - Automated test `test_torrent_path_traversal_prevention` in `tests/test_milestone_2_security_persistence.py` passed against valid subpaths, directory escapes, absolute paths, and drive escapes.

---

### TASK-06: Advisory Lock and IPC Concurrency Fixes
- **Status:** `VERIFIED FIX`
- **Original Finding:** `FINDING-09 (P2 / SEC)`
- **Files Modified:** `src/core/ipc.py`, `tests/test_systems_and_security.py`
- **Implementation:**
  - Removed `os.unlink(self.lock_path)` from `IPCServer._release_lock()`. Unlocking is performed cleanly via `fcntl.flock(fd, fcntl.LOCK_UN)` and descriptor closure. The advisory lock file is retained on disk to preserve POSIX mutual exclusion for other processes waiting on the inode.
  - Implemented strict umask `0o077` during Unix domain socket binding.
  - Added `threading.BoundedSemaphore(10)` to `_listen_loop()` to prevent thread exhaustion attacks.
- **Verification:**
  - Automated tests `test_ipc_advisory_lock_retention_and_concurrency` and `test_TC_IPC_04_advisory_lock_cleanup_on_stop` verified clean lock release, socket unlinking, lock retention, and immediate re-acquisition by subsequent instances.

---

### TASK-07: UUID-Based Playlist Item Tracking
- **Status:** `VERIFIED FIX`
- **Original Finding:** `FINDING-07 (P2)`
- **Files Modified:** `src/ui/playlist_view.py`
- **Implementation:**
  - Added internal UUID tracking: each playlist item is assigned `item.setdefault("id", uuid.uuid4().hex)`.
  - Expanded `Gtk.ListStore` to 5 columns (`int, str, str, str, str`), storing the UUID in the hidden 5th column.
  - Refactored `_on_drag_end()` to map rows by UUID rather than `item["path"]`. Duplicate tracks (multiple identical paths) now retain their individual identities and reordered positions without data loss.
- **Verification:**
  - Automated test `test_playlist_duplicate_preservation_on_drag_end` in `tests/test_milestone_2_security_persistence.py` confirmed that a playlist with duplicate entries can be reversed/reordered while preserving all items and updating the SQLite database.

---

## 3. Milestone 2 Test Summary

| Test Suite | Tests Run | Result | Duration |
|:---|:---:|:---:|:---:|
| `tests/test_milestone_2_security_persistence.py` | 3 | **PASS** | 0.049s |
| `tests/test_torrent_streaming.py` | 18 | **PASS** | 4.630s |
| `tests/test_ipc.py` | 13 | **PASS** | 2.120s |
| `tests/test_playlist_view.py` | 7 | **PASS** | 3.271s |
| `tests/test_systems_and_security.py` | 53 | **PASS** | 5.644s |

**Total:** 94 tests passed with 0 failures and 0 errors.
