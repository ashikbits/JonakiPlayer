# CLI, IPC & Desktop Integration Specification

This document details the command-line interface, inter-process communication protocol, and Linux desktop integration standards for **Jonaki for Linux**, reverse-engineered from `CmdLine64.txt` and Windows IPC patterns.

---

## 1. Command-Line Interface (100% Parity with Windows Jonaki)

Jonaki for Linux accepts both standard POSIX flags (`--flag`) and native Jonaki Windows switches (`/switch` and `-switch`):

```bash
jonaki [content ...] [/switch ...]
```

### 1.1 Content Arguments

| Syntax | Description | Example |
| :--- | :--- | :--- |
| `"file_or_url"` | Local file, directory, or remote URL. Wildcards (`*`, `?`) supported. | `jonaki /path/to/movie.mkv` |
| `"url\Title"` | Remote URL with a custom display title separated by backslash. | `jonaki "https://stream.m3u8\Live News"` |
| `-` | Stream media directly from standard input (pipe). | `yt-dlp -o - "URL" \| jonaki -` |

### 1.2 Switch Reference Table

| Switch | POSIX Equivalent | Description |
| :--- | :--- | :--- |
| `/filedlg` | `--file-dialog` | Opens the Open File dialog immediately on launch. |
| `/urldlg` | `--url-dialog` | Opens the Open URL dialog immediately on launch. |
| `/folderdlg`| `--folder-dialog` | Opens the Open Directory dialog immediately on launch. |
| `/simple` | `--file-navigator`| Opens the built-in File Navigator panel. |
| `/cap` | `--screen-capture`| Starts desktop screen capture mode. |
| `/cam` | `--device-capture`| Opens the default webcam / V4L2 device. |
| `/dvd` | `--dvd` | Plays default optical DVD drive or ISO. |
| `/cd[:drive]` | `--cd[=drive]` | Plays Audio CD from specified drive. |
| `/add` | `--add` | Appends specified file(s) to the end of the current playlist. |
| `/insert` | `--insert` | Inserts file(s) directly below the currently playing item. |
| `/autoplay` | `--autoplay` | Automatically resumes playback of the last played media item. |
| `/same` | `--same` | Loads specified files as synchronized multiple streams. |
| `/sort` | `--sort` | Sorts specified items alphabetically before enqueuing. |
| `/randomize`| `--randomize` | Shuffles specified items randomly before enqueuing. |
| `/new` | `--new-instance` | Launches a new independent player process (bypassing single-instance). |
| `/current` | `--current-instance`| Forces playback in the already running instance. |
| `/clipboard`| `--clipboard` | Reads URL or path from system clipboard and begins playback. |
| `/seek=time`| `--seek=time` | Seeks immediately to timestamp (`hh:mm:ss.ms` or integer seconds). |
| `/sub=file` | `--subtitle=file` | Explicitly loads external subtitle file or URL with media. |
| `/aud=file` | `--audio=file` | Explicitly loads external audio track or URL with media. |
| `/user_agent=ua` | `--user-agent=ua` | Custom `User-Agent` header for network streaming requests. |
| `/referer=ref` | `--referer=ref` | Custom `Referer` header for HTTP(S) requests. |
| `/headers=hdr` | `--headers=hdr` | Additional HTTP headers (formatted as `Key: Value\r\n...`). |
| `/title=text` | `--title=text` | Overrides the window title and OSD media title. |
| `/volume=val` | `--volume=val` | Sets initial playback volume (0 to 100). |
| `config="preset"` | `--config=preset`| Activates a named configuration profile preset. |

---

## 2. Inter-Process Communication (IPC) Socket Protocol

To manage single-instance enforcement and command delegation between processes, Jonaki for Linux uses a Unix domain socket:
$$\text{Socket Path} = \$XDG\_RUNTIME\_DIR/\text{jonaki\_ipc.sock}$$

### 2.1 Protocol Format
Messages are formatted as single-line JSON objects terminated with a newline (`\n`):

#### Client Request (Command Dispatch)
```json
{
  "command": "open",
  "items": [
    {
      "path": "/home/user/Videos/video.mp4",
      "subtitles": ["/home/user/Videos/video.srt"],
      "audio": null,
      "title": null
    }
  ],
  "mode": "enqueue_or_play",
  "seek_pts": 125.5,
  "volume": 80,
  "config": "Default"
}
```

#### Server Response
```json
{
  "status": "ok",
  "active_item": "/home/user/Videos/video.mp4",
  "playlist_size": 12
}
```

### 2.2 IPC Command Actions
- `open`: Open files or URLs (modes: `replace`, `add`, `insert`).
- `play`, `pause`, `play_pause`, `stop`.
- `seek`: Relative offset (`+10`, `-5`) or absolute seconds (`120.0`).
- `set_volume`: Volume level (0-100) or delta (`+5`, `-5`).
- `set_mute`: Boolean or toggle.
- `cycle_audio`, `cycle_sub`: Switch active tracks.
- `take_snapshot`: Capture current frame to disk.
- `get_status`: Query active playback state, position, duration, and track info.

---

## 3. MPRIS2 D-Bus Interface

Jonaki registers on the session D-Bus under the well-known name:
`org.mpris.MediaPlayer2.jonaki`

### 3.1 `org.mpris.MediaPlayer2`
- `CanQuit`: `true`
- `CanRaise`: `true`
- `HasTrackList`: `false`
- `Identity`: `"Jonaki"`
- `SupportedUriSchemes`: `["file", "http", "https", "ftp", "rtsp", "smb"]`
- `SupportedMimeTypes`: `["video/*", "audio/*", "application/vnd.apple.mpegurl"]`
- `Raise()`: Brings the Jonaki window to the front.
- `Quit()`: Gracefully exits the player.

### 3.2 `org.mpris.MediaPlayer2.Player`
- **Properties**:
  - `PlaybackStatus`: `"Playing"`, `"Paused"`, or `"Stopped"`.
  - `LoopStatus`: `"None"`, `"Track"`, or `"Playlist"`.
  - `Rate`: Float (e.g. `1.0`).
  - `Shuffle`: Boolean.
  - `Metadata`: Dictionary containing:
    - `mpris:trackid`: Unique object path.
    - `mpris:length`: Duration in microseconds.
    - `xesam:title`: Title of the playing media.
    - `xesam:artist`: Array of artist names.
    - `xesam:album`: Album title.
    - `mpris:artUrl`: File URI to album art or video thumbnail.
  - `Volume`: Float (0.0 to 1.0+).
  - `Position`: Current playback time in microseconds.
  - `CanPlay`: `true`
  - `CanPause`: `true`
  - `CanSeek`: `true`
  - `CanControl`: `true`
- **Methods**:
  - `Play()`, `Pause()`, `PlayPause()`, `Stop()`, `Next()`, `Previous()`.
  - `Seek(Offset)`: Relative seek in microseconds.
  - `SetPosition(TrackId, Position)`: Absolute seek.
  - `OpenUri(Uri)`: Enqueue and play URI.

---

## 4. Desktop Integration Assets

### 4.1 Desktop Entry (`jonaki.desktop`)
```ini
[Desktop Entry]
Name=Jonaki
GenericName=Media Player
Comment=High-performance multimedia player with advanced subtitle and hardware acceleration features
Exec=jonaki %U
Icon=jonaki
Terminal=false
Type=Application
Categories=AudioVideo;Player;Recorder;TV;
MimeType=video/mp4;video/mkv;video/avi;video/webm;video/x-matroska;audio/mpeg;audio/flac;audio/ogg;
Keywords=video;audio;player;subtitles;jonaki;streaming;
```

### 4.2 MIME Associations & App Icons
- The Jonaki icon atlas (`extracted_jonaki/Logos/Jonaki.png`) is installed into `/usr/share/icons/hicolor/scalable/apps/jonaki.svg` and standard PNG resolution buckets (16x16 up to 512x512).
