"""Local media engine: backsound synthesis, frame extraction, concat, and VO/backsound mux.

This module has NO external API dependency — only ffmpeg (bundled via imageio-ffmpeg),
numpy and scipy. These routines are the validated, deterministic core of the pipeline.
"""
from __future__ import annotations
import os
import re
import subprocess

import imageio.v2 as imageio
import imageio_ffmpeg
import numpy as np
from scipy.io import wavfile
from scipy.signal import butter, sosfilt

FF = imageio_ffmpeg.get_ffmpeg_exe()
SR = 44100


# --------------------------------------------------------------------------- #
# ffmpeg helpers
# --------------------------------------------------------------------------- #
def video_duration(path: str) -> float:
    """Return duration in seconds by parsing ffmpeg stderr."""
    out = subprocess.run([FF, "-i", path], capture_output=True, text=True).stderr
    m = re.search(r"Duration: (\d+):(\d+):(\d+\.\d+)", out)
    if not m:
        raise RuntimeError(f"could not read duration of {path}")
    h, mi, s = m.groups()
    return int(h) * 3600 + int(mi) * 60 + float(s)


def extract_last_frame(mp4: str, out_png: str) -> str:
    """Save the second-to-last frame (cleaner than the very last) as a PNG.

    Used to chain shots: the last frame of clip N becomes the start image of clip N+1.
    """
    reader = imageio.get_reader(mp4, "ffmpeg")
    n = reader.count_frames()
    frame = reader.get_data(max(0, n - 2))
    imageio.imwrite(out_png, frame)
    reader.close()
    return out_png


def normalize_clip(src: str, dst: str) -> str:
    """Copy/transcode a provider clip into a concat-friendly mp4."""
    p = subprocess.run([FF, "-y", "-i", src, "-c", "copy", dst], capture_output=True)
    if p.returncode != 0 or not os.path.exists(dst):
        subprocess.run(
            [FF, "-y", "-i", src, "-c:v", "libx264", "-pix_fmt", "yuv420p", dst],
            capture_output=True,
        )
    return dst


def concat_clips(clips: list[str], out: str) -> str:
    """Concatenate clips into a single silent video."""
    work = os.path.dirname(out) or "."
    listf = os.path.join(work, "_concat.txt")
    with open(listf, "w") as f:
        for c in clips:
            f.write(f"file '{os.path.abspath(c)}'\n")
    p = subprocess.run(
        [FF, "-y", "-f", "concat", "-safe", "0", "-i", listf, "-c", "copy", out],
        capture_output=True, text=True,
    )
    if p.returncode != 0 or not os.path.exists(out):
        subprocess.run(
            [FF, "-y", "-f", "concat", "-safe", "0", "-i", listf,
             "-c:v", "libx264", "-pix_fmt", "yuv420p", out],
            capture_output=True,
        )
    return out


# --------------------------------------------------------------------------- #
# Backsound synthesis (no music-gen API needed)
# --------------------------------------------------------------------------- #
def _adsr(n: int, a: float, d: float, sustain: float, r: float) -> np.ndarray:
    env = np.ones(n)
    ai, di, ri = int(a * SR), int(d * SR), int(r * SR)
    if ai:
        env[:ai] = np.linspace(0, 1, ai)
    if di:
        env[ai:ai + di] = np.linspace(1, sustain, di)
    env[ai + di:n - ri] = sustain
    if ri:
        env[n - ri:] = np.linspace(sustain, 0, ri)
    return env


def _note(freq: float, dur: float, vol: float, detune: float = 0.0) -> np.ndarray:
    n = int(dur * SR)
    t = np.linspace(0, dur, n, False)
    sig = np.sin(2 * np.pi * freq * t)
    if detune:
        sig += 0.5 * np.sin(2 * np.pi * freq * (1 + detune) * t)
    sig += 0.3 * np.sin(2 * np.pi * freq * 0.5 * t)  # sub-octave for warmth
    return sig * _adsr(n, 0.01, 0.08, 0.65, dur * 0.3) * vol


def make_backsound(duration: float, out_wav: str, energy: str = "viral") -> str:
    """Synthesize a warm, loopable backing track.

    energy="viral" -> maj7 pad + plucky arpeggio + 4-on-the-floor kick.
    energy="calm"  -> maj7 pad only.
    """
    total = int(duration * SR)
    out = np.zeros(total)
    # maj7 chord progression: C - Am - F - G
    prog = [
        [261.63, 329.63, 392.00, 493.88],
        [220.00, 261.63, 329.63, 392.00],
        [174.61, 220.00, 261.63, 329.63],
        [196.00, 246.94, 293.66, 392.00],
    ]
    bar = 2.0
    i = 0
    while i * bar < duration:
        chord = prog[i % 4]
        start = int(i * bar * SR)
        seg = np.zeros(int(bar * SR) + SR)
        for f in chord:
            seg[:int(bar * SR) + int(0.4 * SR)] += _note(f, bar + 0.4, 0.12, 0.004)
        if energy == "viral":
            for k, f in enumerate(chord):  # plucky upward arp
                ps = int(k * 0.25 * SR)
                pl = int(0.22 * SR)
                tt = np.linspace(0, 0.22, pl, False)
                seg[ps:ps + pl] += np.sin(2 * np.pi * f * 2 * tt) * np.exp(-tt * 14) * 0.10
        end = min(start + len(seg), total)
        out[start:end] += seg[:end - start]
        i += 1
    if energy == "viral":
        beat = 0.5
        j = 0
        while j * beat < duration:
            ks = int(j * beat * SR)
            kl = int(0.12 * SR)
            tt = np.linspace(0, 0.12, kl, False)
            fsw = 110 * np.exp(-tt * 30) + 45  # pitch-swept kick
            if ks + kl <= total:
                out[ks:ks + kl] += np.sin(2 * np.pi * np.cumsum(fsw) / SR) * np.exp(-tt * 22) * 0.18
            j += 1
    sos = butter(4, 3500 / (SR / 2), btype="low", output="sos")
    out = sosfilt(sos, out)
    tt = np.linspace(0, duration, total, False)
    out *= 0.92 + 0.08 * np.sin(2 * np.pi * 2.0 * tt)  # gentle tremolo
    out = out / (np.max(np.abs(out)) + 1e-6) * 0.62
    wavfile.write(out_wav, SR, (out * 32767).astype(np.int16))
    return out_wav


# --------------------------------------------------------------------------- #
# Mux: voice-over + ducked backsound onto the silent video
# --------------------------------------------------------------------------- #
def to_wav(src: str, out_wav: str) -> str:
    subprocess.run([FF, "-y", "-i", src, "-ar", str(SR), "-ac", "1", out_wav],
                   check=True, capture_output=True)
    return out_wav


def mux_audio(silent_video: str, out: str, vo_wav: str | None = None,
              bg_wav: str | None = None) -> str:
    """Mux VO and/or synthesized backsound onto a silent video.

    When both are present, the backsound is side-chain compressed (ducked) under the
    VO. The VO is padded with silence to the full video length so the compressor keeps
    running for the whole clip (otherwise it stops when the VO ends and -shortest would
    truncate the video).
    """
    vdur = video_duration(silent_video)
    inputs = ["-i", silent_video]

    if vo_wav and bg_wav:
        inputs += ["-i", vo_wav, "-i", bg_wav]
        fc = (
            f"[1:a]apad=whole_dur={vdur:.2f},volume=1.0,asplit=2[vo][voc];"
            f"[2:a]volume=0.32[bgr];"
            f"[bgr][voc]sidechaincompress=threshold=0.025:ratio=10:attack=15:release=350[bgd];"
            f"[vo][bgd]amix=inputs=2:duration=longest,alimiter=limit=0.95[a]"
        )
    elif vo_wav:
        inputs += ["-i", vo_wav]
        fc = "[1:a]volume=1.0,alimiter=limit=0.95[a]"
    elif bg_wav:
        inputs += ["-i", bg_wav]
        fc = "[1:a]volume=0.5,alimiter=limit=0.95[a]"
    else:
        normalize_clip(silent_video, out)
        return out

    cmd = ([FF, "-y"] + inputs +
           ["-filter_complex", fc, "-map", "0:v", "-map", "[a]",
            "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", out])
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"mux failed: {p.stderr[-500:]}")
    return out
