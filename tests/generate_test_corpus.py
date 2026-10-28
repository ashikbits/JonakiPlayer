#!/usr/bin/env python3
"""
Synthetic media corpus generator for Jonaki Player QA test suite.
Generates small, deterministic test media files using ffmpeg and native python.
"""

import os
import subprocess
import sys

CORPUS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "corpus"))

def run_cmd(cmd: list[str]) -> None:
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if res.returncode != 0:
        print(f"Error running command: {' '.join(cmd)}\n{res.stderr}", file=sys.stderr)
        raise RuntimeError(f"Command failed with code {res.returncode}")

def create_subtitles(corpus_dir: str):
    srt_content = """1
00:00:00,500 --> 00:00:02,000
Hello, this is a test subtitle!

2
00:00:02,500 --> 00:00:04,500
Jonaki Player Playback Test.
"""
    srt_path = os.path.join(corpus_dir, "subtitles_sample.srt")
    with open(srt_path, "w", encoding="utf-8") as f:
        f.write(srt_content)

    ass_content = """[Script Info]
Title: Sample ASS Subtitle
ScriptType: v4.00+
Collisions: Normal
PlayDepth: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,20,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,1,0,2,10,10,10,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:00.50,0:00:02.00,Default,,0,0,0,,{\\b1}Hello{\\b0}, styled ASS subtitle!
Dialogue: 0,0:00:02.50,0:00:04.50,Default,,0,0,0,,Jonaki Player Advanced SubStation Alpha.
"""
    ass_path = os.path.join(corpus_dir, "subtitles_sample.ass")
    with open(ass_path, "w", encoding="utf-8") as f:
        f.write(ass_content)

    vtt_content = """WEBVTT

00:00.500 --> 00:02.000
Hello, WebVTT subtitle!

00:02.500 --> 00:04.500
Jonaki Player WebVTT Test.
"""
    vtt_path = os.path.join(corpus_dir, "subtitles_sample.vtt")
    with open(vtt_path, "w", encoding="utf-8") as f:
        f.write(vtt_content)

def generate_corpus():
    os.makedirs(CORPUS_DIR, exist_ok=True)
    print(f"Generating corpus in: {CORPUS_DIR}")

    # Subtitles
    create_subtitles(CORPUS_DIR)

    # 1. valid_h264_aac.mp4 (5s, 320x240, 30fps, keyframe every 0.5s)
    h264_mp4 = os.path.join(CORPUS_DIR, "valid_h264_aac.mp4")
    run_cmd([
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "testsrc=duration=5:size=320x240:rate=30",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=5",
        "-c:v", "libx264", "-g", "15", "-pix_fmt", "yuv420p", "-preset", "ultrafast",
        "-c:a", "aac", "-b:a", "128k",
        h264_mp4
    ])

    # 2. valid_vp9_opus.webm (5s, 320x240, 30fps, keyframe every 0.5s)
    vp9_webm = os.path.join(CORPUS_DIR, "valid_vp9_opus.webm")
    run_cmd([
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "testsrc=duration=5:size=320x240:rate=30",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=5",
        "-c:v", "libvpx-vp9", "-g", "15", "-b:v", "500k",
        "-c:a", "libopus", "-b:a", "96k",
        vp9_webm
    ])

    # 3. audio_only.flac
    flac_path = os.path.join(CORPUS_DIR, "audio_only.flac")
    run_cmd([
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=3",
        "-c:a", "flac",
        flac_path
    ])

    # 4. audio_only.mp3
    mp3_path = os.path.join(CORPUS_DIR, "audio_only.mp3")
    run_cmd([
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=3",
        "-c:a", "libmp3lame", "-b:a", "192k",
        mp3_path
    ])

    # 5. video_only_hevc.mkv
    hevc_mkv = os.path.join(CORPUS_DIR, "video_only_hevc.mkv")
    run_cmd([
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "testsrc=duration=3:size=320x240:rate=30",
        "-an",
        "-c:v", "libx265", "-pix_fmt", "yuv420p", "-preset", "ultrafast",
        hevc_mkv
    ])

    # 6. multi_audio_tracks.mkv (2 audio streams: eng 440Hz, spa 880Hz)
    multi_mkv = os.path.join(CORPUS_DIR, "multi_audio_tracks.mkv")
    run_cmd([
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "testsrc=duration=3:size=320x240:rate=30",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=3",
        "-f", "lavfi", "-i", "sine=frequency=880:duration=3",
        "-map", "0:v", "-map", "1:a", "-map", "2:a",
        "-metadata:s:a:0", "language=eng", "-metadata:s:a:0", "title=English 440Hz",
        "-metadata:s:a:1", "language=spa", "-metadata:s:a:1", "title=Spanish 880Hz",
        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        multi_mkv
    ])

    # 7. movie_with_subs.mkv (embedded subtitles)
    srt_path = os.path.join(CORPUS_DIR, "subtitles_sample.srt")
    movie_subs = os.path.join(CORPUS_DIR, "movie_with_subs.mkv")
    run_cmd([
        "ffmpeg", "-y",
        "-i", h264_mp4,
        "-i", srt_path,
        "-map", "0:v", "-map", "0:a", "-map", "1:s",
        "-c:v", "copy", "-c:a", "copy", "-c:s", "srt",
        "-metadata:s:s:0", "language=eng", "-metadata:s:s:0", "title=English Subtitles",
        movie_subs
    ])

    # 8. corrupted_header.mp4
    corrupted_mp4 = os.path.join(CORPUS_DIR, "corrupted_header.mp4")
    with open(corrupted_mp4, "wb") as f:
        f.write(b"\x00\x00\x00\x20ftypmp42\x00\x00\x00\x00" + b"\xff\x00\xde\xad\xbe\xef" * 100)

    # 9. empty_file.mp4 (0 bytes)
    empty_mp4 = os.path.join(CORPUS_DIR, "empty_file.mp4")
    with open(empty_mp4, "wb") as f:
        pass

    # 10. Unicode & special character filenames
    special_name_1 = os.path.join(CORPUS_DIR, "file [test] #1 (2026) & special.mkv")
    run_cmd(["cp", h264_mp4, special_name_1])

    special_name_2 = os.path.join(CORPUS_DIR, "test_ünicødé_日本語.mp4")
    run_cmd(["cp", h264_mp4, special_name_2])

    # 11. Additional media formats for compatibility testing:
    # AVI container
    avi_path = os.path.join(CORPUS_DIR, "valid_mpeg4.avi")
    run_cmd([
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "testsrc=duration=3:size=320x240:rate=30",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=3",
        "-c:v", "mpeg4", "-c:a", "libmp3lame",
        avi_path
    ])

    # MPEG-TS container
    ts_path = os.path.join(CORPUS_DIR, "valid_stream.ts")
    run_cmd([
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "testsrc=duration=3:size=320x240:rate=30",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=3",
        "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac",
        ts_path
    ])

    # AV1 video in MKV or MP4
    av1_mkv = os.path.join(CORPUS_DIR, "valid_av1.mkv")
    run_cmd([
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "testsrc=duration=2:size=320x240:rate=30",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
        "-c:v", "libsvtav1", "-b:v", "400k",
        "-c:a", "libopus",
        av1_mkv
    ])

    # High FPS (60 / 120 FPS)
    high_fps = os.path.join(CORPUS_DIR, "high_fps_120.mp4")
    run_cmd([
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "testsrc=duration=2:size=320x240:rate=120",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
        "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac",
        high_fps
    ])

    # Unusual / odd resolution
    odd_res = os.path.join(CORPUS_DIR, "odd_res_333x555.mp4")
    # Libx264 requires even dimensions for yuv420p, so use libvpx-vp9 or yuv444p
    run_cmd([
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "testsrc=duration=2:size=333x555:rate=30",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
        "-c:v", "libvpx-vp9", "-c:a", "libopus",
        odd_res
    ])

    # Truncated midstream
    trunc_path = os.path.join(CORPUS_DIR, "truncated_midstream.mp4")
    with open(h264_mp4, "rb") as f_in:
        raw_data = f_in.read()
    with open(trunc_path, "wb") as f_out:
        f_out.write(raw_data[:len(raw_data) // 2])

    print("Corpus generation complete.")

if __name__ == "__main__":
    generate_corpus()
