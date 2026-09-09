"""Build a timelapse of one day's stills with ffmpeg, off the request thread.

A Pi 3 encodes H264 in software well under realtime, so a few hundred frames takes
long enough that blocking a waitress thread on it would look like a hang. start()
kicks off a worker and the UI polls status(). Frames are symlinked into a scratch
dir as a numbered sequence because ffmpeg's image demuxer wants %05d, not the
arbitrary timestamps the captures are named with.
"""
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path

import config
from utilities import visits

_lock = threading.Lock()
_state = {"state": "idle", "message": "", "filename": None, "day": None, "frames": 0}


def status():
    with _lock:
        return dict(_state)


def _set(**kw):
    with _lock:
        _state.update(kw)


def _frames_for(day, media_files):
    """Stills from `day`, oldest first, capped so the encode stays bounded."""
    rows = []
    for name in media_files:
        if not name.endswith(".jpg"):
            continue
        ts = visits.parse_ts(name)
        if ts and ts.date().isoformat() == day:
            rows.append((ts, name))
    rows.sort()
    return [name for _, name in rows][:config.TIMELAPSE_MAX_FRAMES]


def _build(day, frames):
    tmp = Path(tempfile.mkdtemp(prefix="birdcam_tl_"))
    try:
        for i, name in enumerate(frames):
            (tmp / f"f_{i:05d}.jpg").symlink_to(config.MEDIA_DIR / name)
        out = config.MEDIA_DIR / f"timelapse_{day.replace('-', '')}.mp4"
        cmd = [
            "ffmpeg", "-y",
            "-framerate", str(config.TIMELAPSE_FPS),
            "-i", str(tmp / "f_%05d.jpg"),
            "-vf", f"scale={config.TIMELAPSE_WIDTH}:-2",
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "28",
            "-pix_fmt", "yuv420p",
            str(out),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            tail = proc.stderr.strip().splitlines()[-3:]
            _set(state="error", message=" / ".join(tail) or "ffmpeg failed")
            return
        _set(state="done", filename=out.name,
             message=f"{len(frames)} frames -> {out.name}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def start(day, media_files):
    """Kick off a build. Returns (ok, message)."""
    with _lock:
        if _state["state"] == "running":
            return False, "A timelapse is already building"
    frames = _frames_for(day, media_files)
    if len(frames) < 2:
        return False, f"Only {len(frames)} still(s) for {day} — need at least 2"
    _set(state="running", message=f"Encoding {len(frames)} frames…",
         filename=None, day=day, frames=len(frames))
    threading.Thread(target=_build, args=(day, frames), daemon=True).start()
    return True, f"Building a timelapse from {len(frames)} frames"
