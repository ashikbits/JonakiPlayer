# Complete Feature Specification: Jonaki for Linux

This document details the exhaustive feature matrix of **Jonaki for Linux**, cataloged directly from the reverse-engineered Windows Jonaki resource dictionaries (`Language/English.ini`, `Menus/SimpleMenu.xml`, `CmdLine64.txt`) and binary class metadata.

---

## 1. Feature Category Matrix

### 1.1 Media Formats & Containers
- **Video Containers**: Matroska (MKV), MP4, AVI, WebM, FLV, OGM, OGV, TS, M2TS, MTS, VOB, MPG, MPEG, WMV, ASF, RM, RMVB, MOV, 3GP, DIVX, BIK, DSM, DPG, DVR-MS.
- **Video Codecs**: AV1, HEVC/H.265, AVC/H.264, VP9, VP8, MPEG-1, MPEG-2, MPEG-4 Part 2, VC-1, RealVideo, Theora, ProRes, Motion JPEG, Cinepak.
- **Audio Formats**: MP3, AAC, AC3 (Dolby Digital), EAC3 (Dolby Digital Plus), TrueHD, DTS, DTS-HD, FLAC, ALAC, Opus, Vorbis, WMA, PCM, WAV, AIFF, APE (Monkey's Audio), TTA, Musepack (MPC), CDDA, MOD, XM, IT, S3M.
- **Subtitle Formats**: Advanced SubStation Alpha (ASS), SubStation Alpha (SSA), SubRip (SRT), SAMI (SMI), WebVTT (VTT), MicroDVD (SUB), VobSub (IDX/SUB), Blu-ray PGS (SUP), DVB subtitles, Teletext, TTML, LRC (synchronized lyrics).
- **Network Streaming Protocols**: HTTP/HTTPS, HLS (m3u8), MPEG-DASH (mpd), RTSP, RTMP, FTP, FTPS, WebDAV, MMS, standard input streaming (`-`).

---

### 1.2 Video Processing & Enhancements

| Feature | Description | Implementation Mechanism |
| :--- | :--- | :--- |
| **Hardware Video Acceleration** | Zero-copy GPU decoding of 4K/8K 10-bit/12-bit content | VA-API, NVDEC, Vulkan Video, VDPAU |
| **HDR to SDR Tone-Mapping** | Conversion of HDR10/HLG color volumes to SDR displays | `libplacebo` tone-mapping algorithms (Reinhard, Mobius, Hable, BT.2390) |
| **Deinterlacing** | Motion-adaptive deinterlacing for 1080i/480i interlaced broadcasts | `bwdif`, `yadif`, hardware VA-API deinterlace |
| **Color Controls** | Real-time Brightness, Contrast, Saturation, and Hue adjustment | OpenGL/Vulkan shader ProcAmp adjustments |
| **Pixel Shaders** | Post-processing effects (Sharpen, Adaptive Sharpen, Denoise, Levels, Procamp) | GLSL user shaders executed via libplacebo |
| **Motion Interpolation** | Smooth 60fps/144fps frame doubling/interpolation | VapourSynth / AviSynth MVTools integration |
| **Aspect Ratio & Sizing** | Fit to Window, 16:9, 4:3, 2.35:1, 1.85:1, custom ratio, Pan & Scan | Viewport scaling and affine transform matrix |
| **Rotation & Flipping** | Rotate 90°, 180°, 270°, Auto-rotate from EXIF metadata, Horz/Vert Flip | Texture coordinate manipulation |
| **360° / VR Playback** | Interactive 360° equirectangular projection with mouse drag / FOV zoom | Spherical panoramic shader projection |
| **3D Stereoscopic Playback** | Side-by-side, Top-and-bottom, Anaglyph (Red/Cyan), Page flip | Multi-view split shader and color filtering |

---

### 1.3 Audio Processing & DSP

| Feature | Description | Implementation Mechanism |
| :--- | :--- | :--- |
| **10-Band Graphic Equalizer** | Frequency bands: 31Hz, 62Hz, 125Hz, 250Hz, 500Hz, 1kHz, 2kHz, 4kHz, 8kHz, 16kHz | IIR peaking biquad filters |
| **Equalizer Presets** | Pop, Rock, Classical, Jazz, Club, Vocal, Techno, Full Bass, Soft | Pre-configured gain curves (-12dB to +12dB) |
| **Audio Normalization** | Prevents drastic volume spikes between scenes | Look-ahead peak limiter and RMS normalizer |
| **Channel Remapping** | Upmixing Stereo (2.0) to Surround (5.1/7.1), or Downmixing to Stereo | Matrix mixer with configurable center/subwoofer levels |
| **Voice Processing** | Voice isolation (karaoke removal) and Voice enhancement | Center channel phase cancellation and vocal band boost |
| **Pitch & Speed Control** | Speed from 0.2x to 12.0x with optional pitch compensation (scaletempo) | High-quality WSOLA / Rubberband time-stretching |
| **Audio Delay / Sync** | Synchronize audio track with video (-10.0s to +10.0s in 50ms increments) | Buffer queue offset delay |

---

### 1.4 Subtitle Engine & AI Capabilities

| Feature | Description | Implementation Mechanism |
| :--- | :--- | :--- |
| **Simultaneous Multi-Subtitles** | Display primary subtitles at bottom, secondary subtitles at top/custom | Dual-channel `libass` compositor |
| **Real-Time Translation** | Live translation of foreign subtitle lines during playback | Plugins for Google, DeepL, Papago, Bing, LibreTranslate |
| **Local LLM Subtitle Translation**| Real-time translation via local AI models | REST JSON integration with LM Studio / Ollama / vLLM |
| **Speech-to-Text Subtitles** | Generate live subtitles for videos without subtitle tracks | Whisper.cpp with Vulkan compute acceleration |
| **Online Subtitle Search** | Automatically find matching subtitles on the web | OpenSubtitles, SubDL, Podnapisi scrapers |
| **Subtitle Styling** | Font family, size, bold, italic, color, outline width, shadow, blur | Complete CSS / ASS styling engine |
| **Subtitle Synchronization** | Live subtitle timing adjustment (Shift + Left/Right, Alt + Left/Right) | Real-time PTS offset modification |
| **Word Lookup / Dictionary** | Click subtitle words to view dictionary definition | Embedded dictionary popup / web search |

---

### 1.5 Playlists, History & Bookmarks

| Feature | Description | Implementation Mechanism |
| :--- | :--- | :--- |
| **Hierarchical Playlists** | Multi-album tabs, nested folders, drag-and-drop file adding | GtkTreeView / custom DSF skin list widget |
| **Playback History & Resume** | Remembers playback position, audio track, and subtitle for every file | SQLite3 database (`mediadb.sqlite`) |
| **Visual Bookmarks** | Save timeline bookmarks (`P` key) with thumbnail snapshots (`H` menu) | Frame thumbnail caching and seekbar markers |
| **A-B Repeat Mode** | Seamlessly loop segment between points A (`[` key) and B (`]` key) | High-precision seek loop controller |
| **Smart Sorting & Shuffling** | Natural alphanumeric sorting, randomize, sort by date/size | In-memory sorting algorithms |
| **Folder Auto-Add** | Automatically enqueue adjacent files from the same directory | Directory scanning on media load |

---

### 1.6 Capture & Recording Suite

| Feature | Description | Implementation Mechanism |
| :--- | :--- | :--- |
| **Single Frame Capture** | Instantly save current frame at original resolution to disk (`Ctrl+P`) | Raw video frame dump to PNG, JPEG, WebP |
| **Consecutive Frame Capture** | Capture continuous frame bursts at specified intervals | Automated frame capture sequence |
| **Animated GIF Creation** | Create animated GIF or WebP clips from video segments (`Ctrl+Alt+G`) | FFmpeg palettegen / paletteuse GIF encoder |
| **Thumbnail Storyboard Sheet** | Generate contact sheet grid with video metadata & timestamps (`Ctrl+Alt+S`)| Grid compositor with metadata header |
| **Stream / Video Recording** | Record live streaming video or capture input directly to MKV/MP4 (`Ctrl+A`) | Real-time FFmpeg remuxing or re-encoding |
| **Screen / Webcam Capture** | Stream desktop display (PipeWire/X11) or webcam (V4L2) (`Ctrl+S`, `Ctrl+J`) | Linux PipeWire Portal / V4L2 device input |

---

### 1.7 On-Screen Display (OSD) & Playback Info (Tab Key)

Pressing `Tab` opens the iconic Jonaki Playback Information overlay:
- **Container / Format**: File path, container format, overall bitrate, duration.
- **Video Stream**: Codec FourCC, profile, resolution, display aspect ratio, frame rate (FPS), color space (BT.709, BT.2020), pixel format (YUV420P, YUV420P10LE).
- **Hardware Decoder**: Active decoder status (`[HW: VAAPI]` or `[SW: FFmpeg]`).
- **Rendering Performance**: Output FPS, dropped frames, sync jitter, display refresh rate.
- **Audio Stream**: Codec, sample rate (e.g. 48000 Hz), channels (e.g. 6 ch 5.1), bitrate.
- **Output Device**: Active audio sink (PipeWire, PulseAudio, ALSA), resampler latency.

---

### 1.8 Control Box (F6 Key)

The Jonaki Control Box provides quick access to five tabbed adjustment panels:
1. **Audio**: 10-band equalizer sliders, preamp slider, preset selector, 3D spatializer, normalizer toggle.
2. **Video**: Brightness, Contrast, Saturation, Hue sliders; deinterlacing mode; screen rotation.
3. **Subtitles**: Subtitle font size, vertical position, horizontal position, sync offset slider.
4. **Playback**: Speed slider (0.2x - 3.0x), A-B repeat controls, jump interval selector.
5. **Color / Shaders**: Pixel shader selector (Sharpen, Deband, Levels), night mode toggle.

---

## 2. Complete Keyboard Shortcuts Reference

The following table documents the default Jonaki keyboard shortcut layout replicated in the Linux version:

| Category | Keybinding | Command ID | Action |
| :--- | :--- | :--- | :--- |
| **Playback** | `Space` | `CMD_MEDIA_PLAY_PAUSE` | Toggle Play / Pause |
| | `Enter` | `CMD_FULLSCREEN` | Toggle Fullscreen |
| | `Ctrl + Enter` | `CMD_FULLSCREEN_STRETCH` | Fullscreen (Stretch to fit) |
| | `F4` | `CMD_MEDIA_CLOSE` | Close Playback / Stop |
| | `Ctrl + Y` | `CMD_REOPEN` | Reopen current or last played item |
| **Seeking** | `Left` / `Right` | `CMD_SEEK_5S` | Seek Backward / Forward 5 seconds |
| | `Ctrl + Left` / `Right` | `CMD_SEEK_30S` | Seek Backward / Forward 30 seconds |
| | `Shift + Left` / `Right` | `CMD_SEEK_60S` | Seek Backward / Forward 1 minute |
| | `Ctrl + Alt + Left` / `Right` | `CMD_SEEK_300S` | Seek Backward / Forward 5 minutes |
| | `Ctrl + Shift + Left` / `Right` | `CMD_SEEK_KEYFRAME` | Seek to Previous / Next Keyframe |
| | `[` / `]` | `CMD_AB_REPEAT_START/END` | Set A / B point for A-B Repeat Loop |
| | `\` | `CMD_AB_REPEAT_CLEAR` | Clear A-B Repeat Loop |
| | `Backspace` | `CMD_SEEK_START` | Seek to beginning of video |
| **Speed** | `Z` | `CMD_SPEED_RESET` | Reset Playback Speed to 1.0x |
| | `X` | `CMD_SPEED_DOWN` | Decrease Playback Speed (-0.1x) |
| | `C` | `CMD_SPEED_UP` | Increase Playback Speed (+0.1x) |
| **Audio** | `Up` / `Down` | `CMD_VOLUME_UP/DOWN` | Increase / Decrease Volume (+2% / -2%) |
| | `M` | `CMD_AUDIO_MUTE` | Toggle Audio Mute |
| | `Shift + Up` / `Down` | `CMD_AUDIO_BOOST` | Audio Boost Preamp |
| | `A` | `CMD_CYCLE_AUDIO_TRACK` | Cycle to next audio stream |
| | `Shift + [` / `]` | `CMD_AUDIO_SYNC_ADJUST` | Adjust Audio Sync (-0.05s / +0.05s) |
| | `Shift + /` | `CMD_AUDIO_SYNC_RESET` | Reset Audio Sync to 0ms |
| **Subtitles** | `Alt + O` | `CMD_SUB_OPEN` | Open Subtitle File dialog |
| | `Alt + Y` | `CMD_SUB_RELOAD` | Reload Subtitles |
| | `Alt + H` | `CMD_SUB_VISIBILITY` | Toggle Subtitle Visibility |
| | `S` | `CMD_CYCLE_SUB_TRACK` | Cycle to next subtitle stream |
| | `Alt + Left` / `Right` | `CMD_SUB_SYNC_500MS` | Subtitle Sync (-0.5s / +0.5s) |
| | `Alt + [` / `]` | `CMD_SUB_SYNC_50MS` | Subtitle Sync (-0.05s / +0.05s) |
| | `Alt + /` | `CMD_SUB_SYNC_RESET` | Reset Subtitle Sync |
| | `Alt + PgUp` / `PgDn` | `CMD_SUB_SIZE_ADJUST` | Increase / Decrease Subtitle Font Size |
| | `Alt + Up` / `Down` | `CMD_SUB_POS_ADJUST` | Move Subtitle Position Up / Down |
| **Video Adjust** | `Q` | `CMD_COLOR_RESET` | Reset Video Colors (Brightness/Contrast) |
| | `W` / `E` | `CMD_BRIGHTNESS_ADJUST` | Brightness -1% / +1% |
| | `R` / `T` | `CMD_CONTRAST_ADJUST` | Contrast -1% / +1% |
| | `Y` / `U` | `CMD_SATURATION_ADJUST` | Saturation -1% / +1% |
| | `I` / `O` | `CMD_HUE_ADJUST` | Hue -1° / +1° |
| | `V` | `CMD_CYCLE_ASPECT_RATIO` | Cycle Aspect Ratio modes |
| | `Ctrl + F11` | `CMD_DEINTERLACE_TOGGLE`| Toggle Deinterlacing |
| **Capture** | `Ctrl + P` | `CMD_CAPTURE_FRAME` | Save Current Frame to default folder |
| | `Ctrl + E` | `CMD_CAPTURE_FRAME_AS` | Save Current Frame As... (file dialog) |
| | `Ctrl + C` | `CMD_CAPTURE_TO_CLIPBOARD`| Copy Current Frame to Clipboard |
| | `Ctrl + Alt + S` | `CMD_CREATE_STORYBOARD`| Create Thumbnail Storyboard Sheet |
| | `Ctrl + Alt + G` | `CMD_CREATE_GIF` | Create Animated GIF / WebP clip |
| | `Ctrl + A` | `CMD_STREAM_RECORD` | Record Stream / Video to file |
| **Bookmarks** | `P` | `CMD_BOOKMARK_ADD` | Add Bookmark at current timestamp |
| | `H` | `CMD_BOOKMARK_MENU` | Show Bookmarks list menu |
| **Panels** | `Tab` | `CMD_OSD_PLAYINFO` | Toggle Technical Playback Info (OSD) |
| | `F5` | `CMD_PREFERENCES_DIALOG`| Open Preferences Dialog |
| | `F6` | `CMD_CONTROL_BOX` | Open Control Box (Equalizer/Video/Sub) |
| | `F7` | `CMD_EQUALIZER_DIALOG` | Open Audio Equalizer Panel |
| | `F8` / `F12` | `CMD_PLAYLIST_WINDOW` | Open Playlist Window |
| | `F1` | `CMD_ABOUT_DIALOG` | About Jonaki |
