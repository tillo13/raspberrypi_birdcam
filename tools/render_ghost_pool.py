"""Render ghost lines (one per line, # = comment) into ghost/pool/NN.mp3 in the Ghost preset:
Kokoro af_nicole at 0.85 speed, then an ffmpeg echo chain. Runs on the Mac (the Pi 3 can't run Kokoro).
Usage: ~/.claude/skills/tuf/kokoro/venv/bin/python tools/render_ghost_pool.py LINES.txt"""
import subprocess, sys
from pathlib import Path

import soundfile as sf
from kokoro_onnx import Kokoro

MODELS = Path.home() / ".claude/skills/tuf/kokoro/models"
ECHO = ("highpass=f=800,apad=pad_dur=3,"
        "aecho=0.8:0.9:180|420|800|1300|2000|2900:0.55|0.45|0.35|0.28|0.2|0.14,"
        "volume=2.6,alimiter=limit=0.95")

lines = [l.strip() for l in Path(sys.argv[1]).read_text().splitlines()
         if l.strip() and not l.startswith("#")]
out = Path(__file__).resolve().parent.parent / "ghost" / "pool"
out.mkdir(parents=True, exist_ok=True)
k = Kokoro(str(MODELS / "kokoro-v1.0.onnx"), str(MODELS / "voices-v1.0.bin"))
for i, text in enumerate(lines, 1):
    samples, rate = k.create(text, voice="af_nicole", speed=0.85, lang="en-us")
    raw = out / f"{i:02d}_raw.wav"
    sf.write(raw, samples, rate)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(raw), "-af", ECHO,
                    "-ac", "1", "-b:a", "128k", str(out / f"{i:02d}.mp3")], check=True)
    raw.unlink()
    print(f"{i:02d}  {text}", flush=True)
