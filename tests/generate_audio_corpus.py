"""
Jonaki Player - Audio Test Corpus Generator
Generates reproducible test signals for evaluating audio enhancement:
- Quiet dialogue and speech
- Normally mastered music
- Dynamic movie audio with wide dynamic range
- Heavily compressed loud music
- Strong bass transients
- Very quiet recordings with background noise
- Multichannel 5.1 audio
- Different sample rates & bit depths (44.1kHz 16-bit, 48kHz 24-bit, 96kHz 24-bit)
- Test tones, silence, and dynamic sweeps
"""

import os
import wave
import struct
import math
import subprocess


CORPUS_DIR = os.path.join(os.path.dirname(__file__), "audio_corpus")


def ensure_corpus_dir():
    os.makedirs(CORPUS_DIR, exist_ok=True)


def write_wav_16bit(filename: str, samples_l: list, samples_r: list = None, sample_rate: int = 48000):
    filepath = os.path.join(CORPUS_DIR, filename)
    num_channels = 2 if samples_r is not None else 1
    num_frames = len(samples_l)

    with wave.open(filepath, "w") as wf:
        wf.setnchannels(num_channels)
        wf.setsampwidth(2)  # 16-bit
        wf.setframerate(sample_rate)

        raw_bytes = bytearray()
        for i in range(num_frames):
            sl = max(-32768, min(32767, int(samples_l[i] * 32767)))
            raw_bytes.extend(struct.pack("<h", sl))
            if samples_r is not None:
                sr = max(-32768, min(32767, int(samples_r[i] * 32767)))
                raw_bytes.extend(struct.pack("<h", sr))
        wf.writeframes(raw_bytes)
    return filepath


def write_wav_24bit(filename: str, samples_l: list, samples_r: list = None, sample_rate: int = 96000):
    filepath = os.path.join(CORPUS_DIR, filename)
    num_channels = 2 if samples_r is not None else 1
    num_frames = len(samples_l)

    with wave.open(filepath, "w") as wf:
        wf.setnchannels(num_channels)
        wf.setsampwidth(3)  # 24-bit
        wf.setframerate(sample_rate)

        raw_bytes = bytearray()
        max_val = 8388607
        min_val = -8388608
        for i in range(num_frames):
            sl = max(min_val, min(max_val, int(samples_l[i] * max_val)))
            raw_bytes.extend(sl.to_bytes(3, byteorder="little", signed=True))
            if samples_r is not None:
                sr = max(min_val, min(max_val, int(samples_r[i] * max_val)))
                raw_bytes.extend(sr.to_bytes(3, byteorder="little", signed=True))
        wf.writeframes(raw_bytes)
    return filepath


def generate_quiet_dialogue():
    # 6 seconds of simulated quiet speech: pulsed formants around 200, 750, 1500, 2500 Hz
    sample_rate = 48000
    duration = 6.0
    num_samples = int(sample_rate * duration)
    samples = [0.0] * num_samples

    # Syllables cadence: 4 syllables per second with natural phrasing
    for i in range(num_samples):
        t = i / sample_rate
        # Envelope: syllables repeating every 0.25s with 0.18s vocalization
        syllable_cycle = t % 0.25
        if syllable_cycle < 0.18:
            env = math.sin(math.pi * syllable_cycle / 0.18) ** 2
            # Formant synthesis for speech vowel /a/ /o/
            vocal = (0.5 * math.sin(2 * math.pi * 180 * t) +
                     0.3 * math.sin(2 * math.pi * 750 * t) +
                     0.15 * math.sin(2 * math.pi * 1500 * t) +
                     0.05 * math.sin(2 * math.pi * 2500 * t))
            # Level: very quiet dialogue (-28 to -30 LUFS range, ~0.03 peak)
            samples[i] = vocal * env * 0.035
        else:
            samples[i] = 0.0

    write_wav_16bit("quiet_dialogue.wav", samples, samples, sample_rate)


def generate_normal_music():
    # 6 seconds of pop/acoustic musical progression: A minor (220, 261, 329 Hz), F major, C major, G major
    sample_rate = 48000
    duration = 6.0
    num_samples = int(sample_rate * duration)
    samples_l = [0.0] * num_samples
    samples_r = [0.0] * num_samples

    chords = [
        (220.0, 261.63, 329.63),  # Am
        (174.61, 220.0, 261.63),  # F
        (261.63, 329.63, 392.0),  # C
        (196.0, 246.94, 293.66),  # G
    ]

    for i in range(num_samples):
        t = i / sample_rate
        chord_idx = min(3, int(t / 1.5))
        f1, f2, f3 = chords[chord_idx]

        # Bass kick / percussion beat every 0.75s
        beat = (t % 0.75)
        kick = math.sin(2 * math.pi * 55 * beat) * math.exp(-beat * 12) if beat < 0.3 else 0.0

        # Chord synthesizer
        harmonics_l = (0.35 * math.sin(2 * math.pi * f1 * t) +
                       0.25 * math.sin(2 * math.pi * f2 * t) +
                       0.20 * math.sin(2 * math.pi * f3 * t))
        harmonics_r = (0.25 * math.sin(2 * math.pi * f1 * t + 0.3) +
                       0.35 * math.sin(2 * math.pi * f2 * t + 0.2) +
                       0.20 * math.sin(2 * math.pi * f3 * t + 0.1))

        # Target around -16 to -18 LUFS
        samples_l[i] = (harmonics_l * 0.25) + (kick * 0.25)
        samples_r[i] = (harmonics_r * 0.25) + (kick * 0.25)

    write_wav_16bit("normal_music.wav", samples_l, samples_r, sample_rate)


def generate_dynamic_movie():
    # 8 seconds: 0-4s very quiet whisper/footsteps (-32 LUFS), 4-8s massive explosion/brass chord (-2 dBFS peak)
    sample_rate = 48000
    duration = 8.0
    num_samples = int(sample_rate * duration)
    samples_l = [0.0] * num_samples
    samples_r = [0.0] * num_samples

    for i in range(num_samples):
        t = i / sample_rate
        if t < 4.0:
            # Whisper / dialogue section
            whisper = (math.sin(2 * math.pi * 300 * t) * 0.015 +
                       math.sin(2 * math.pi * 1800 * t) * 0.008)
            samples_l[i] = whisper
            samples_r[i] = whisper
        else:
            # Action / explosion section with deep sub-bass and brass chords
            texp = t - 4.0
            sub_bass = math.sin(2 * math.pi * 40 * texp) * math.exp(-texp * 0.5) * 0.5
            brass = (math.sin(2 * math.pi * 110 * texp) * 0.3 +
                     math.sin(2 * math.pi * 220 * texp) * 0.2 +
                     math.sin(2 * math.pi * 440 * texp) * 0.15)
            # Peak approaching -0.8 dBFS (~0.91 amplitude)
            sig = (sub_bass + brass) * 0.95
            samples_l[i] = sig
            samples_r[i] = sig

    write_wav_16bit("dynamic_movie.wav", samples_l, samples_r, sample_rate)


def generate_loud_compressed_music():
    # 5 seconds of dense, brickwalled audio (-9 LUFS, peak 0.98)
    sample_rate = 48000
    duration = 5.0
    num_samples = int(sample_rate * duration)
    samples_l = [0.0] * num_samples
    samples_r = [0.0] * num_samples

    for i in range(num_samples):
        t = i / sample_rate
        val = 0.0
        # Multi-octave dense sum
        for freq in [60, 120, 240, 480, 960, 1920, 3840]:
            val += math.sin(2 * math.pi * freq * t)
        val /= 4.0  # Dense sum
        # Soft-saturate to simulate brickwall limiting
        val_sat = math.tanh(val * 1.8) * 0.96
        samples_l[i] = val_sat
        samples_r[i] = val_sat

    write_wav_16bit("loud_compressed_music.wav", samples_l, samples_r, sample_rate)


def generate_bass_transients():
    # 5 seconds: 40 Hz sub-bass kick transient every 1.0 second, peak 0.92 (-0.7 dBFS)
    sample_rate = 48000
    duration = 5.0
    num_samples = int(sample_rate * duration)
    samples = [0.0] * num_samples

    for i in range(num_samples):
        t = i / sample_rate
        bt = t % 1.0
        if bt < 0.4:
            # 45 Hz sine decaying exponentially
            env = math.exp(-bt * 8.0)
            samples[i] = math.sin(2 * math.pi * 45 * bt) * env * 0.92
        else:
            samples[i] = 0.0

    write_wav_16bit("bass_transients.wav", samples, samples, sample_rate)


def generate_quiet_with_noise():
    # 6 seconds: quiet speech tone (-32 LUFS) mixed with continuous background noise (-46 dBFS)
    sample_rate = 48000
    duration = 6.0
    num_samples = int(sample_rate * duration)
    samples = [0.0] * num_samples

    # Pseudo-random noise generator using linear congruential formula
    seed = 123456789
    for i in range(num_samples):
        t = i / sample_rate
        # Background hum / hiss at ~0.005 peak (-46 dBFS)
        seed = (1103515245 * seed + 12345) & 0x7fffffff
        noise = ((seed / 0x7fffffff) * 2.0 - 1.0) * 0.005
        # Low 60Hz hum
        hum = math.sin(2 * math.pi * 60 * t) * 0.004

        # Speech burst intermittently
        speech = 0.0
        if (t % 1.5) < 0.8:
            speech = (math.sin(2 * math.pi * 400 * t) * 0.03 +
                      math.sin(2 * math.pi * 1200 * t) * 0.015)

        samples[i] = speech + noise + hum

    write_wav_16bit("quiet_with_noise.wav", samples, samples, sample_rate)


def generate_multichannel_5_1():
    # Generate 5.1 channel WAV (6 channels: FL, FR, FC, LFE, BL, BR)
    filepath = os.path.join(CORPUS_DIR, "multichannel_5_1.wav")
    sample_rate = 48000
    duration = 5.0
    num_samples = int(sample_rate * duration)
    with wave.open(filepath, "w") as wf:
        wf.setnchannels(6)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        raw_bytes = bytearray()
        for i in range(num_samples):
            t = i / sample_rate
            fl = int(max(-1.0, min(1.0, math.sin(2 * math.pi * 440 * t) * 0.2)) * 32767)
            fr = int(max(-1.0, min(1.0, math.sin(2 * math.pi * 554 * t) * 0.2)) * 32767)
            fc = int(max(-1.0, min(1.0, math.sin(2 * math.pi * 1000 * t) * 0.3)) * 32767)
            lfe = int(max(-1.0, min(1.0, math.sin(2 * math.pi * 50 * t) * 0.4)) * 32767)
            bl = int(max(-1.0, min(1.0, math.sin(2 * math.pi * 330 * t) * 0.15)) * 32767)
            br = int(max(-1.0, min(1.0, math.sin(2 * math.pi * 392 * t) * 0.15)) * 32767)
            raw_bytes.extend(struct.pack("<6h", fl, fr, fc, lfe, bl, br))
        wf.writeframes(raw_bytes)


def generate_samplerate_variations():
    # 44.1kHz 16-bit
    sr1 = 44100
    n1 = int(sr1 * 4.0)
    s1 = [math.sin(2 * math.pi * 440 * (i / sr1)) * 0.3 for i in range(n1)]
    write_wav_16bit("stereo_44k1_16bit.wav", s1, s1, sr1)

    # 96kHz 24-bit
    sr2 = 96000
    n2 = int(sr2 * 4.0)
    s2 = [math.sin(2 * math.pi * 440 * (i / sr2)) * 0.3 for i in range(n2)]
    write_wav_24bit("hi_res_96k_24bit.wav", s2, s2, sr2)


def generate_test_tones_and_silence():
    # 4 seconds: 1s silence, 1s 1kHz @ -18 dBFS, 1s 1kHz @ -0.5 dBFS, 1s dynamic sweep -50 to 0 dBFS
    sample_rate = 48000
    duration = 4.0
    num_samples = int(sample_rate * duration)
    samples = [0.0] * num_samples

    for i in range(num_samples):
        t = i / sample_rate
        if t < 1.0:
            samples[i] = 0.0
        elif t < 2.0:
            # -18 dBFS = 10^(-18/20) ~ 0.1259
            samples[i] = math.sin(2 * math.pi * 1000 * t) * 0.1259
        elif t < 3.0:
            # -0.5 dBFS = 10^(-0.5/20) ~ 0.9441
            samples[i] = math.sin(2 * math.pi * 1000 * t) * 0.9441
        else:
            # Linear amplitude sweep from 0.00316 (-50 dBFS) to 1.0 (0 dBFS)
            frac = t - 3.0
            amp = 0.00316 + frac * (1.0 - 0.00316)
            samples[i] = math.sin(2 * math.pi * 1000 * t) * amp

    write_wav_16bit("test_tones_and_silence.wav", samples, samples, sample_rate)


def generate_adversarial_signals():
    # 1. 22kHz near-Nyquist sine with 45-degree phase offset (0 dBFS) at 44.1kHz
    sr = 44100
    n = sr * 2
    s_nyq = [math.sin(2 * math.pi * 22000 * (i / sr) + math.pi / 4) for i in range(n)]
    write_wav_16bit("adversarial_nyquist_sine.wav", s_nyq, s_nyq, sr)

    # 2. 4kHz full-scale square wave (generates odd harmonics up to Nyquist)
    s_sq = [1.0 if math.sin(2 * math.pi * 4000 * (i / sr)) >= 0 else -1.0 for i in range(n)]
    write_wav_16bit("adversarial_square_4k.wav", s_sq, s_sq, sr)

    # 3. Unit impulse train (every 200 samples)
    s_imp = [1.0 if (i % 200 == 0) else 0.0 for i in range(n)]
    write_wav_16bit("adversarial_impulse_train.wav", s_imp, s_imp, sr)

    # 4. Realistic speech podcast with natural sibilants and phrasing
    sr_sp = 48000
    n_sp = sr_sp * 6
    s_speech = [0.0] * n_sp
    for i in range(n_sp):
        t = i / sr_sp
        word_cycle = t % 0.6
        if word_cycle < 0.45:
            env = math.sin(math.pi * word_cycle / 0.45) ** 2
            # Voice pitch + formants + sibilance
            vocal = (0.4 * math.sin(2 * math.pi * 130 * t) +
                     0.3 * math.sin(2 * math.pi * 800 * t) +
                     0.2 * math.sin(2 * math.pi * 2200 * t) +
                     0.1 * math.sin(2 * math.pi * 6500 * t))
            s_speech[i] = vocal * env * 0.05  # -26 LUFS quiet podcast
    write_wav_16bit("real_speech_podcast.wav", s_speech, s_speech, sr_sp)


def main():
    ensure_corpus_dir()
    print("Generating audio test corpus in:", CORPUS_DIR)
    generate_quiet_dialogue()
    generate_normal_music()
    generate_dynamic_movie()
    generate_loud_compressed_music()
    generate_bass_transients()
    generate_quiet_with_noise()
    generate_multichannel_5_1()
    generate_samplerate_variations()
    generate_test_tones_and_silence()
    generate_adversarial_signals()
    print("All audio corpus test signals generated successfully.")


if __name__ == "__main__":
    main()
