# Jonaki Player — Audio Enhancement Test Plan & Measurement Methodology

**Document Version:** 1.0.0  
**Author:** Senior Audio Quality Assurance & Desktop Application Tester  
**Repository:** `ashik60/JonakiPlayer` (`/home/ashik/Data/Projects/Jonaki`)  
**Date:** 2026-10-27  

---

## 1. Overview & Test Objectives

The objective of this test plan is to establish a rigorous, objective, and reproducible audio evaluation protocol for the **Jonaki Audio Enhancement System**. 

The testing protocol verifies that the enhanced audio engine:
1. Makes quiet dialogue and low-volume recordings noticeably and comfortably louder at normal listening levels (+4.5 to +6.0 dB perceived loudness boost).
2. Controls high-energy peaks and explosions without digital clipping or DAC inter-sample distortion ($\text{True Peak} \le -0.7\text{ dBTP}$).
3. Preserves musical dynamics and natural transient punch without audible pumping, breathing, or squashing.
4. Operates with near-zero CPU overhead and zero impact on audio/video synchronization.
5. Persists user preferences and integrates cleanly into the GUI and keyboard accelerators.

---

## 2. Test Media Corpus Specification

All test signals are deterministically generated via [`tests/generate_audio_corpus.py`](file:///home/ashik/Data/Projects/Jonaki/tests/generate_audio_corpus.py) and stored under [`tests/audio_corpus/`](file:///home/ashik/Data/Projects/Jonaki/tests/audio_corpus/). In addition, a real-world reference media file is tested from the local system.

| Fixture Name | Format & Sample Rate | Duration | Baseline I (LUFS) | Baseline TP (dBTP) | Test Purpose & Audio Characteristics |
| :--- | :--- | :---: | :---: | :---: | :--- |
| `quiet_dialogue.wav` | 48 kHz, 16-bit PCM, Stereo | 6.0s | -39.8 | -29.7 | Simulated low-level speech with vowel formants (180, 750, 1500, 2500 Hz). Tests dialogue boost. |
| `normal_music.wav` | 48 kHz, 16-bit PCM, Stereo | 6.0s | -18.9 | -7.9 | Balanced acoustic/pop music with harmonic progression and kick drum. Tests musical dynamics. |
| `dynamic_movie.wav` | 48 kHz, 16-bit PCM, Stereo | 8.0s | -9.5 | -1.0 | 4s quiet whisper (-32 LUFS) followed by 4s massive explosion (-1.0 dBFS). Tests dynamic range & limiter. |
| `loud_compressed_music.wav` | 48 kHz, 16-bit PCM, Stereo | 5.0s | -1.4 | -0.8 | Dense, multi-octave brickwalled audio near 0 dBFS. Tests limiter ceiling and clipping prevention. |
| `bass_transients.wav` | 48 kHz, 16-bit PCM, Stereo | 5.0s | -15.4 | -1.1 | 45 Hz sub-bass kick transients with fast 5ms attack. Tests low-frequency limiter stability. |
| `quiet_with_noise.wav` | 48 kHz, 16-bit PCM, Stereo | 6.0s | -31.0 | -27.2 | Quiet speech tones mixed with continuous -46 dBFS background hiss and hum. Tests noise amplification. |
| `multichannel_5_1.wav` | 48 kHz, 16-bit PCM, 6-Channel | 5.0s | -9.7 | -8.0 | 5.1 layout (FL, FR, FC, LFE, BL, BR) with center speech. Tests multichannel downmixing & stability. |
| `stereo_44k1_16bit.wav` | 44.1 kHz, 16-bit PCM, Stereo | 4.0s | -18.2 | -10.5 | Redbook standard audio. Tests sample-rate compatibility and resampling. |
| `hi_res_96k_24bit.wav` | 96 kHz, 24-bit PCM, Stereo | 4.0s | -18.2 | -10.5 | Studio high-resolution audio. Tests high-bit-depth buffer handling. |
| `test_tones_and_silence.wav`| 48 kHz, 16-bit PCM, Stereo | 4.0s | -14.1 | -0.0 | Silence, -18 dBFS tone, -0.5 dBFS tone, and dynamic amplitude sweep (-50 to 0 dBFS). |
| `Dhivara [8K]...webm` | 48 kHz Opus, Stereo (Real Video)| 15.0s | -12.0 | +1.3 | Commercial high-resolution music video soundtrack with wide frequency response and loud peaks. |

---

## 3. Objective Measurement Procedure

All objective audio measurements are executed using FFmpeg's ITU-R BS.1770-4 compliant `ebur128` filter with 4x oversampling true-peak detection:

```bash
ffmpeg -nostats -i <input_file> -af "<dsp_filter_chain>,ebur128=peak=true" -f null -
```

### Metrics Recorded:
1. **Integrated Loudness ($I$, LUFS):** Measures overall perceived loudness across the entire duration according to the K-weighted loudness curve.
2. **Loudness Range (LRA, LU):** Measures the statistical distribution of loudness levels, reflecting the dynamic contrast between quiet and loud parts.
3. **True Peak (TP, dBTP):** Detects inter-sample peaks using 4x oversampling interpolation to prevent analog clipping upon DAC playback.
4. **Gain Reduction & Limiter Engagement:** Verifies that limiter attenuation engages smoothly during peak overshoots and releases without audible distortion.
5. **CPU Overhead & Thread Utilization:** Monitored via Linux `resource.getrusage` and `/proc/<pid>/stat`.

---

## 4. Subjective Listening Comparison Protocols

To ensure audio quality is genuinely preserved and not merely optimized for arbitrary meter readings, two distinct listening evaluations are performed:

### Protocol 1: Normal-Use Comparison (Fixed Volume)
- **Method:** Set hardware and player volume to a fixed 70% level. Play media first with Enhancement **OFF** (Bit-Perfect), then switch to Enhancement **ON** (Balanced / Default).
- **Evaluation Criteria:**
  - Is dialogue effortlessly intelligible without leaning forward or straining?
  - Does the overall sound feel full and present rather than thin and distant?
  - Are loud explosions or music climaxes jarring, painful, or distorted?

### Protocol 2: Loudness-Matched Comparison (Quality & Artifacts)
- **Method:** Calculate the integrated loudness difference ($\Delta I$) between enhanced and unprocessed output. Attenuate the enhanced output by $-\Delta I$ dB using an external precision digital attenuator so that both versions play back at the exact same perceived loudness.
- **Evaluation Criteria:**
  - **Pumping / Breathing:** Do background sounds or room ambiance unnaturally swell when dialogue pauses?
  - **Harshness / Sibilance:** Are "s", "t", "sh" sounds piercing or strident?
  - **Bass Distortion:** Does sub-bass rumble, flap, or buzz during heavy kick drum hits?
  - **Transient Smearing:** Are drum rimshots and acoustic guitar plucks dulled or flat?
  - **Noise Floor:** Is background tape hiss or microphone room noise amplified to an annoying degree?

---

## 5. Automated Test Suite Architecture

The automated test suite in [`tests/test_audio_enhancement.py`](file:///home/ashik/Data/Projects/Jonaki/tests/test_audio_enhancement.py) incorporates 16 test cases covering:

1. **Model & Filter Chain Generation:**
   - `test_default_constructor_bit_perfect`: Ensures `AudioDSPChain()` produces `""` filter string.
   - `test_enable_enhancement_default_preset`: Verifies default gain, compressor, and limiter parameters.
   - `test_all_presets_filter_generation`: Validates Off, Gentle, Balanced, Dialogue Focus, and Dynamic presets.
   - `test_no_duplicate_volume_stages`: Validates single unified `volume=` filter when PreAmp boost is applied.
   - `test_bounded_normalizer_interaction`: Verifies `dynaudnorm` uses safe bounded gain `m=6.0` when enhancement is active.
2. **Settings Persistence:**
   - `test_persistence_defaults_and_updates`: Verifies that enabled state, preset choice, and custom gain survive application restart in SQLite database.
3. **Engine Integration & Resilience:**
   - `test_engine_set_audio_enhancement`: Verifies in-process `libmpv` property updates without engine stall.
   - `test_filter_resilience_on_invalid_filter`: Tests graceful fallback when invalid filter parameters are passed.
4. **UI Integration:**
   - `test_fresh_install_enabled_by_default`: Asserts enhancement is active on clean install.
   - `test_shift_e_shortcut_toggle`: Tests `Shift+E` keyboard accelerator toggle.
   - `test_command_dispatch_presets`: Tests context menu command dispatching.
   - `test_control_box_audio_tab_sync`: Tests F6 Control Box checkbutton, combo, and scale synchronization.
5. **Objective Corpus Metrics:**
   - `test_quiet_dialogue_perceived_loudness`: Asserts $\ge 4.5\text{ dB}$ loudness gain on quiet speech.
   - `test_loud_compressed_music_ceiling`: Asserts true peak $\le 0.0\text{ dBTP}$ on brickwalled audio.
   - `test_dynamic_movie_crest_factor`: Asserts LRA $\ge 15.0\text{ LU}$ on dynamic movie audio.
   - `test_bass_transient_preservation`: Asserts true peak $\le 0.0\text{ dBTP}$ on sub-bass kicks.
