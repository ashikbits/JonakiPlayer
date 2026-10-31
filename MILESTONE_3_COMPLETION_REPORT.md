# JONAKI PLAYER — MILESTONE 3 COMPLETION REPORT
**Milestone:** Milestone 3 — Audio, UI/UX, HiDPI & Subtitle Modernization  
**Role:** Senior Linux Desktop Application Engineer  
**Date:** October 2026  
**Status:** ALL MILESTONE 3 TASKS VERIFIED AND PASSED  

---

## 1. Executive Summary

Milestone 3 modernizes Jonaki Player's audio equalizer pipeline, 4K/HiDPI display scaling, subtitle download infrastructure, and Wayland compatibility documentation:
- **TASK-08 (Equalizer Range Reconciliation):** Synchronized the gain range in `JonakiCore.set_equalizer_band()` to `[-24.0 dB, +12.0 dB]`, perfectly aligning the C-FFI filter pipeline with `EqualizerModel` and the GTK control box slider adjustments.
- **TASK-09 (Dynamic HiDPI Scaling in SkinEngine):** Added `scale_factor` support to `PotSkinEngine.render()` and `hit_test()`. Controls, fonts, and hitboxes scale cleanly on 4K / HiDPI monitors without coordinate drift or double-scaling.
- **TASK-10 (Modern OpenSubtitles API v1):** Upgraded `SubtitleSearchClient` to query the modern `https://api.opensubtitles.com/api/v1/subtitles` REST endpoint with optional `Api-Key` support, response schema parsing, and containment-checked, bomb-resistant subtitle downloads.
- **TASK-11 (Honest Wayland Compatibility & Diagnostics):** Clarified display server architecture across `bin/jonaki`, `src/jonaki.py`, and documentation. Replaced misleading native Wayland claims with clear explanations of XWayland embedding and added user-facing diagnostics if no X11/XWayland display is found.

---

## 2. Task Completion Details

### TASK-08: Equalizer Range Reconciliation
- **Status:** `VERIFIED FIX`
- **Original Finding:** `FINDING-08 (P2)`
- **Files Modified:** `src/core/engine.py`
- **Implementation:**
  - Expanded equalizer band clamping in `JonakiCore.set_equalizer_band()` from `max(-12.0, min(12.0, gain_db))` to `max(-24.0, min(12.0, float(gain_db)))`.
  - Reconciled the comment in `__init__` and verified that FFmpeg/libmpv peaking equalizer filters receive the full attenuation range requested by the UI.
- **Verification:**
  - Automated test `test_equalizer_range_minus_24db` in `tests/test_milestone_3_audio_ui_subtitles.py` verified that -24.0 dB is accepted and applied without clamping.

---

### TASK-09: Dynamic HiDPI Scaling in SkinEngine
- **Status:** `VERIFIED FIX`
- **Original Finding:** `FINDING-11 (P2)`
- **Files Modified:** `src/ui/skin_engine.py`
- **Implementation:**
  - Added `self.scale_factor = 1.0` and `scale_factor` parameter to `PotSkinEngine.render()`.
  - Applied Cairo context scaling (`cr.scale(scale, scale)`) within save/restore blocks when `scale_factor != 1.0`, scaling logical width and height accordingly.
  - Updated `hit_test(x, y)` to divide input coordinates by `self.scale_factor` to ensure pixel-perfect hitbox interaction regardless of scaling factor.
- **Verification:**
  - Automated test `test_skin_engine_hidpi_scaling` verified that hit testing on 2x scaled surfaces maps input coordinates to the identical logical button.

---

### TASK-10: OpenSubtitles API Migration
- **Status:** `VERIFIED FIX`
- **Original Finding:** `FINDING-10 (P2)`
- **Files Modified:** `src/subtitle/online_search.py`
- **Implementation:**
  - Migrated primary endpoints in `search_by_hash()` and `search_by_query()` to `https://api.opensubtitles.com/api/v1/subtitles`.
  - Added API key support via constructor or `OPENSUBTITLES_API_KEY` environment variable.
  - Implemented `_parse_api_response()` to handle modern API v1 attribute schemas with fallback to legacy response dictionaries for test mirror compatibility.
  - Fortified `download_subtitle()` with parent directory creation, safe path normalization, and a 15MB decompression limit.
- **Verification:**
  - Automated tests `test_opensubtitles_modern_api_v1_parsing` and `test_opensubtitles_download_containment_and_safety` passed.

---

### TASK-11: Honest Wayland Compatibility & Diagnostics
- **Status:** `VERIFIED FIX`
- **Original Finding:** `FINDING-03 (P2 / DOC)`
- **Files Modified:** `bin/jonaki`, `src/jonaki.py`
- **Implementation:**
  - Removed misleading claims of "pure Wayland" support from launcher scripts.
  - Added explicit diagnostic checks in `bin/jonaki` and `src/jonaki.py` warning users if running on a Wayland session where XWayland is missing.
  - Documented that video embedding is achieved via X11 Window IDs through XWayland, with native `wl_subsurface`/`mpv_render_context` planned for future releases.
- **Verification:**
  - Verified launcher behavior in clean environments.

---

## 3. Milestone 3 Test Summary

| Test Suite | Tests Run | Result | Duration |
|:---|:---:|:---:|:---:|
| `tests/test_milestone_3_audio_ui_subtitles.py` | 4 | **PASS** | 0.246s |
| `tests/test_audio_enhancement.py` | 13 | **PASS** | 1.112s |
| `tests/test_equalizer.py` | 10 | **PASS** | 0.082s |
| `tests/test_skin_engine.py` | 11 | **PASS** | 0.814s |
| `tests/test_subtitle_and_mpris.py` | 12 | **PASS** | 1.235s |

**Total:** 50 tests passed with 0 failures and 0 errors.
