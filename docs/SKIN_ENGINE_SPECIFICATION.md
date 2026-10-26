# Skin Engine Specification: PotPlayer DSF Architecture

This document specifies the internal structure, layout grammar, and rendering pipeline of PotPlayer's **DSF (Daum Skin Format)** skin engine, reverse-engineered from `extracted_potplayer/Skins/Default.dsf` and `PotPlayer64.dll`.

---

## 1. DSF Archive Structure

A `.dsf` file is a standard ZIP archive compressed with Deflate containing UI layout descriptors, XML definitions, localized string tables, and sprite sheets:

```
Default.dsf (ZIP Archive)
├── Common.txt             # Global layout macros, scrollbar definitions, and StringTable includes
├── BottomVideo.txt        # Video mode bottom control bar (buttons, badges, timebar, volume)
├── BottomAudio.txt        # Audio mode bottom control bar
├── TopCommon.txt          # Titlebar layout (logo, title text, minimize/maximize/close buttons)
├── Title.txt              # Window caption and borders
├── AudioSkin.xml          # Audio-only mode container layout
├── VideoSkin.xml          # Video playback container layout
├── StringTable.txt        # Localized tooltips and label text definitions
├── Main.png               # Main button sprites atlas (Play, Pause, Stop, Seek, Open)
├── BRTool.png             # Bottom-right tool buttons & status badge background plates
├── Control.png            # Control box dialog widgets and sliders
├── Window.png             # Window frame borders, corners, and titlebar buttons
├── Slider.png             # Seekbar and volume slider background tracks and thumb knobs
└── ScrollBar.bmp          # Scrollbar arrows, tracks, and thumbs
```

---

## 2. Layout XML/TXT Grammar

PotPlayer's layout engine uses an XML-like tag hierarchy combined with preprocessor directives (`#include`, `#if`, `#else`, `#endif`).

### 2.1 Supported Elements

| Tag | Attributes | Description |
| :--- | :--- | :--- |
| `<Static>` | `Align`, `Height`, `Width`, `ImageLeft`, `ImageTop`, `ImageWidth`, `ImageHeight`, `LeftMargin`, `RightMargin` | Background panel container supporting 9-slice or centered image blitting. |
| `<Button>` | `CmdID`, `AltCmdID`, `Tooltip`, `ImageLeft`, `ImageTop`, `ImageWidth`, `ImageHeight`, `DownFlag`, `VisParentMinWidth` | Interactive clickable button with normal, hover, pressed, and disabled states. |
| `<Slider>` | `CmdID`, `Alignment`, `Width`, `Height`, `ThumbWidth`, `ThumbHeight`, `ImageLeft`, `BackImageLeft`, `ThumbImageLeft` | Continuous or stepped slider (used for Seekbar and Volume control). |
| `<Label>` | `CmdID`, `Text`, `FontName`, `FontSize`, `ColorX`, `ColorY`, `VertAlignment`, `AutoSize`, `Cursor` | Dynamic or static text label. Color coordinates point into color palette sprites. |
| `<Layout>` | `Align`, `Width`, `Height`, `VisParentMinWidth` | Spacer / padding element controlling layout flow. |
| `<ScrollBar>`| `Name`, `SizingGripperX`, `Length`, `Width` | Custom scrollbar component with arrow buttons, page tracks, and draggable thumb. |

---

## 3. Sprite Sheet Coordinate System & 9-Slice Blitting

In PotPlayer DSF skins, individual UI assets are not stored as separate files. Instead, they reside on shared sprite atlases (primarily `Main.png`, `BRTool.png`, and `Window.png`).

```
┌────────────────────────────────────────────────────────┐
│ Main.png (Sprite Sheet Atlas)                          │
│                                                        │
│  (0, 259) [ Play Button 41x40 ]                        │
│    State 0 (Normal):   X=0,   Y=259, W=41, H=40        │
│    State 1 (Hover):    X=41,  Y=259, W=41, H=40        │
│    State 2 (Pressed):  X=82,  Y=259, W=41, H=40        │
│    State 3 (Disabled): X=123, Y=259, W=41, H=40        │
│                                                        │
│  (164, 259) [ Pause Button 41x40 ]                     │
│    State 0 (Normal):   X=164, Y=259, W=41, H=40        │
│    State 1 (Hover):    X=205, Y=259, W=41, H=40        │
│    State 2 (Pressed):  X=246, Y=259, W=41, H=40        │
│                                                        │
│  (0, 300) [ Stop Button 41x40 ]                        │
│    State 0 (Normal):   X=0,   Y=300, W=41, H=40        │
└────────────────────────────────────────────────────────┘
```

### 3.1 Button State Transitions
Every `<Button>` maps to 4 horizontal slices of width `ImageWidth`:
$$\text{Source } X = \text{ImageLeft} + (\text{StateIndex} \times \text{ImageWidth})$$
- $\text{StateIndex} = 0$: **Normal** (idle state)
- $\text{StateIndex} = 1$: **Hover / Over** (mouse pointer inside button bounds)
- $\text{StateIndex} = 2$: **Pressed / Push** (mouse button held down)
- $\text{StateIndex} = 3$: **Disabled** (action unavailable)

### 3.2 Nine-Slice Scaling Algorithm
For resizable panels like the bottom control bar (`<Static Height='40'>`) and window borders:
1. Four fixed corners (top-left, top-right, bottom-left, bottom-right) copied at 1:1 scale using `LeftMargin` and `RightMargin`.
2. Top and bottom edges horizontally stretched or tiled between margins.
3. Left and right edges vertically stretched or tiled.
4. Center area scaled to fill remaining space.

---

## 4. Seekbar (`CMD_TIMEBAR_CTRL`) Specification

The seekbar is defined in `BottomVideo.txt` as:

```xml
<Slider Align='Client' CmdID='CMD_TIMEBAR_CTRL' Alignment='1' 
        ImageWidth='95' ImageHeight='10' ThumbWidth='11' ThumbHeight='10' 
        ImageLeft='0' ImageTop='179' BackImageLeft='0' BackImageTop='193' 
        AltImageLeft='0' AltImageTop='207' ThumbImageLeft='1' ThumbImageTop='239' 
        LeftMargin='10' RightMargin='10' 
        RepeatAImageLeft='148' RepeatAImageTop='241' 
        RepeatBImageLeft='155' RepeatBImageTop='241' RepeatImageWidth='6' RepeatImageHeight='10'
        BookmarkImageLeft='171' BookmarkImageTop='241' 
        SeamlessImageLeft='188' SeamlessImageTop='241' />
```

### 4.1 Seekbar Layering & Overlays
1. **Background Track** (`BackImageLeft='0'`, `BackImageTop='193'`): Dark unplayed track.
2. **Buffer / Download Progress** (`AltImageLeft='0'`, `AltImageTop='207'`): Cached stream duration bar.
3. **Playback Progress Bar** (`ImageLeft='0'`, `ImageTop='179'`): High-contrast progress bar indicating current time.
4. **Thumb Knob** (`ThumbImageLeft='1'`, `ThumbImageTop='239'`): Draggable playhead knob.
5. **A-B Repeat Range & Pins**:
   - Point A Pin (`RepeatAImageLeft='148'`): Marker flag at start time.
   - Point B Pin (`RepeatBImageLeft='155'`): Marker flag at end time.
   - Loop Segment Highlight: Shaded region between Point A and Point B.
6. **Bookmark Markers** (`BookmarkImageLeft='171'`): Small triangular indicator pins positioned at each saved bookmark PTS.
7. **Hover Thumbnail Preview**: A floating popup window showing a video frame snapshot and timestamp at the mouse hover position.

---

## 5. Bottom Bar Status Badges

PotPlayer features interactive status badges embedded directly in the bottom control bar:

```
[ ▶ ] [ ⏸ ] [ ⏹ ] [ ◀◀ ] [ ▶▶ ] [ 📂 ]  00:14:22 / 02:18:40  [ HW ] [ HDR ] [ H264 ] [ AAC ] [ 2.0 ]   🔊 ━━●━━
```

| Badge Command ID | Default Label | Interactive Behavior |
| :--- | :--- | :--- |
| `CMD_VIDEO_OUT_HW_SW_MESSAGE` | `[HW]` or `[SW]` | Toggles between Hardware Acceleration (VA-API/NVDEC) and Software Decoding (FFmpeg). |
| `ID_VIDEO_PS_SMPTE_2084` | `[HDR]` | Toggles HDR tone-mapping on/off; shows active color transfer curve. |
| `CMD_VIDEO_CODEC_FOURCC_MESSAGE` | `[AVC1]`, `[HEVC]`, etc. | Displays video codec FourCC; clicking opens Codec Info dialog. |
| `CMD_AUDIO_CODEC_TYPE_MESSAGE` | `[AAC]`, `[FLAC]`, etc. | Displays audio codec; clicking opens Audio Stream Selector. |
| `CMD_AUDIO_OUT_NUM_CHANNEL_MESSAGE`| `[2.0]`, `[5.1]`, etc. | Displays channel configuration; clicking opens Channel Downmixing / Upmixing menu. |

---

## 6. Responsive UI Rules (`VisParentMinWidth`)

The skin dynamically responds to window width resizing by hiding lower-priority badges when screen real-estate is constrained:

- `Window Width < 460px`: Hide HW/SW decoder badge.
- `Window Width < 630px`: Hide Video Codec badge.
- `Window Width < 670px`: Hide Audio Codec badge.
- `Window Width < 690px`: Hide Channel Layout badge.
- `Window Width < 700px`: Hide HDR badge.
- `Window Width < 740px`: Hide Download Rate label.

---

## 7. Linux DSF Renderer Implementation

In the Linux implementation, the DSF engine is handled by `PotSkinCompositor`:
1. `zipfile` extracts `Default.dsf` into an in-memory or cached directory.
2. `Cairo` / `Skia` surfaces perform 9-slice tiling and sprite coordinate blitting.
3. GTK / Wayland input events (motion-notify, button-press, button-release, leave-notify) dispatch state changes to buttons and trigger repaints.
4. Double-buffering prevents UI flickering during active video playback.
