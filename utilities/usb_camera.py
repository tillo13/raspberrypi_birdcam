"""Stills from whatever USB (UVC) webcam is plugged in.

Speed first: a background ffmpeg keeps the camera streaming MJPEG at 1080p30 and we
hold the newest frame, so a snap returns what the camera saw a few tens of ms ago
instead of cold-opening the device (measured 2026-10-22 on the Pi 3: ffmpeg start
1.9 s, first 2304x1536 frame 5.1 s, ~19 s for a settled max-size still). The webcam
already JPEG-encodes MJPEG frames, so holding them costs no decode/encode.

capture_max() is the slow path: the biggest mode the device advertises in any
format (C922: 2304x1536 YUYV at 2 fps), with the stream paused around it.

Not tied to one model: the device is found by bus (usb-*) in v4l2-ctl's listing.
"""
import re
import subprocess
import threading
import time

STREAM_SIZE = "1920x1080"
STREAM_FPS = 15           # newest frame <= ~67 ms old; 30 fps cost ~31% of a core to read
STALE_SECONDS = 2.0        # a newest frame older than this means the stream is down
FRESH_WAIT_SECONDS = 6.0   # fast snap waits this long for the stream to (re)start
RETRY_SECONDS = 5.0      # wait before reopening after unplug / ffmpeg exit
SKIP_FRAMES = 10           # first frames after open can be corrupt and unexposed
WARMUP_FRAMES = 8          # max path: let exposure / autofocus settle first
JPEG_QSCALE = 2            # ffmpeg mjpeg quality, 2 = best
_FFMPEG_FORMATS = {"YUYV": "yuyv422", "MJPG": "mjpeg"}
_SOI = b"\xff\xd8\xff"


class NotPluggedIn(RuntimeError):
    """No USB camera on the bus right now (it comes and goes)."""


def find_device():
    """(first /dev/video node, name) of the first USB camera, or None."""
    out = subprocess.run(["v4l2-ctl", "--list-devices"],
                         capture_output=True, text=True).stdout
    for block in out.split("\n\n"):
        lines = block.strip().splitlines()
        if lines and "(usb-" in lines[0] and len(lines) > 1:
            return lines[1].strip(), lines[0].split(" (")[0]
    return None


def largest_mode(dev):
    """(ffmpeg input format, 'WxH') with the most pixels; MJPG wins a tie."""
    out = subprocess.run(["v4l2-ctl", "-d", dev, "--list-formats-ext"],
                         capture_output=True, text=True).stdout
    best, fmt = None, None
    for line in out.splitlines():
        m = re.search(r"'(\w+)'", line)
        if m and "[" in line:
            fmt = m.group(1)
            continue
        m = re.search(r"Size: Discrete (\d+)x(\d+)", line)
        if m and fmt in _FFMPEG_FORMATS:
            w, h = int(m.group(1)), int(m.group(2))
            key = (w * h, fmt == "MJPG")
            if best is None or key > best[0]:
                best = (key, fmt, f"{w}x{h}")
    return (_FFMPEG_FORMATS[best[1]], best[2]) if best else None


def _autofocus_on(dev):
    # Continuous AF (it may have been pinned by hand); a camera without the
    # control just reports an error we don't need.
    subprocess.run(["v4l2-ctl", "-d", dev, "-c", "focus_automatic_continuous=1"],
                   capture_output=True)


class UsbStream:
    def __init__(self):
        self._frame_lock = threading.Lock()
        self._latest = None            # (time, jpeg bytes)
        self._name = None
        self._proc = None
        self._paused = threading.Event()
        self._device_lock = threading.Lock()   # stream vs max capture
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        while True:
            if self._paused.is_set():
                time.sleep(0.1)
                continue
            found = find_device()
            if not found:
                self._name = None
                time.sleep(RETRY_SECONDS)
                continue
            dev, self._name = found
            with self._device_lock:
                if self._paused.is_set():   # a max capture got here first
                    continue
                _autofocus_on(dev)
                # mjpeg2jpeg puts back the Huffman tables UVC cameras leave out, so
                # each frame is a standalone JPEG any viewer can open.
                self._proc = subprocess.Popen(
                    ["ffmpeg", "-loglevel", "error", "-f", "v4l2",
                     "-input_format", "mjpeg", "-video_size", STREAM_SIZE,
                     "-framerate", str(STREAM_FPS), "-i", dev,
                     "-c:v", "copy", "-bsf:v", "mjpeg2jpeg", "-f", "mjpeg", "-"],
                    stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            self._read(self._proc)
            self._proc.wait()
            with self._frame_lock:
                self._latest = None    # unplugged or stopped: nothing current to serve
            if not self._paused.is_set():
                time.sleep(RETRY_SECONDS)

    def _read(self, proc):
        # Frames arrive as back-to-back JPEGs: one is whole once the next SOI shows
        # up. Only the bytes that just arrived get scanned (rescanning the whole
        # frame on every 64 KB chunk put the app at 140% CPU on the Pi 3).
        buf, seen = bytearray(), 0
        while True:
            chunk = proc.stdout.read1(262144)
            if not chunk:
                return
            scan_from = max(len(buf) - 2, 3)
            buf += chunk
            nxt = buf.find(_SOI, scan_from)
            while nxt > 0:
                seen += 1
                if seen > SKIP_FRAMES:
                    with self._frame_lock:
                        self._latest = (time.time(), bytes(buf[:nxt]))
                del buf[:nxt]
                nxt = buf.find(_SOI, 3)

    def capture_photo(self, path):
        """Newest streamed frame (1080p) to path, near-instant.

        Unplugged fails at once. Right after a max capture or a replug the stream
        takes a few seconds to come back, so wait that long for a fresh frame.
        """
        if not find_device():
            raise NotPluggedIn("no USB camera plugged in")
        deadline = time.time() + FRESH_WAIT_SECONDS
        while True:
            with self._frame_lock:
                latest = self._latest
            if latest is not None and time.time() - latest[0] <= STALE_SECONDS:
                break
            if time.time() > deadline:
                raise RuntimeError("no live frame from a USB camera (unplugged or starting)")
            time.sleep(0.1)
        with open(path, "wb") as f:
            f.write(latest[1])
        return path

    def capture_max(self, path):
        """Largest-mode still, ~19 s on a C922. Pauses the stream around it."""
        self._paused.set()
        try:
            if self._proc and self._proc.poll() is None:
                self._proc.terminate()
            with self._device_lock:
                found = find_device()
                if not found:
                    raise NotPluggedIn("no USB camera plugged in")
                dev, name = found
                mode = largest_mode(dev)
                if not mode:
                    raise RuntimeError(f"{name}: no usable capture format")
                input_format, size = mode
                _autofocus_on(dev)
                subprocess.run(
                    ["ffmpeg", "-loglevel", "error", "-y", "-f", "v4l2",
                     "-input_format", input_format, "-video_size", size, "-i", dev,
                     "-vf", f"select=gte(n\\,{WARMUP_FRAMES})", "-frames:v", "1",
                     "-q:v", str(JPEG_QSCALE), path],
                    check=True, capture_output=True, timeout=60)
        finally:
            with self._frame_lock:
                self._latest = None    # don't serve a pre-pause frame as fresh
            self._paused.clear()
        return path

    def status(self):
        """Live check for the snap menu: is a webcam plugged in, and is it streaming."""
        found = find_device()
        with self._frame_lock:
            latest = self._latest
        fresh = latest is not None and time.time() - latest[0] <= STALE_SECONDS
        return {"available": bool(found), "name": found[1] if found else None,
                "streaming": bool(found) and fresh}


_stream = None
_get_lock = threading.Lock()


def get_stream():
    """Return the process-wide UsbStream, starting it on first use."""
    global _stream
    with _get_lock:
        if _stream is None:
            _stream = UsbStream()
    return _stream
