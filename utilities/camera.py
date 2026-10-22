"""Persistent picamera2 camera for Bird Cam — one live camera, many consumers.

Replaces the old per-frame `libcamera-still` subprocess model (and its camera_busy
mutex). The camera opens once; a single background thread pulls low-res frames that
motion detection and the live MJPEG stream both read, while photos and video pull
from the high-res main stream. All hardware access is serialised behind one lock.
"""
import threading
import time

import cv2
from picamera2 import Picamera2
from picamera2.encoders import H264Encoder
from picamera2.outputs import FfmpegOutput

# This is a NoIR module (no IR-cut filter), so the stock ov5647.json tuning — a
# Bayesian AWB with a 21-point colour-temperature curve — is modelling light the
# sensor isn't seeing. ov5647_noir.json sets bayes=0 with no ct_curve, i.e. the
# greyworld balance these modules are supposed to run. Infrared still lands in the
# red channel; only a physical filter fixes that. This just stops the AWB fighting it.
TUNING_FILE = "ov5647_noir.json"

# The module is mounted a quarter-turn off, so stills and the live view get rotated
# back. libcamera's Transform only does hflip/vflip (180 deg), so 90 has to happen
# here. Output becomes portrait; remounting the camera is the fix that doesn't.
ROTATION = 90              # degrees counter-clockwise; 0/90/180/270
_ROTATE_CODES = {90: cv2.ROTATE_90_COUNTERCLOCKWISE,
                 180: cv2.ROTATE_180,
                 270: cv2.ROTATE_90_CLOCKWISE}

MAIN_SIZE = (1920, 1080)   # high-res: photos + video
LORES_SIZE = (640, 480)    # low-res: motion + live stream (Y plane is grayscale)
STREAM_FPS = 15            # cap for the live MJPEG stream
STREAM_QUALITY = 80        # JPEG quality for the live stream
SETTLE_SECONDS = 1.0       # let AE/AWB settle after start

_LORES_W, _LORES_H = LORES_SIZE


class Camera:
    def __init__(self):
        self._picam = Picamera2(tuning=_load_tuning())
        self._picam.configure(self._picam.create_video_configuration(
            main={"size": MAIN_SIZE, "format": "RGB888"},
            lores={"size": LORES_SIZE, "format": "YUV420"},
        ))
        self._cam_lock = threading.Lock()   # serialises all picamera2 access
        self._frame_lock = threading.Lock() # guards the shared latest frame
        self._latest_bgr = None
        self._latest_gray = None
        self._recording = False
        self._running = True
        self._rec_path = None
        self._stream_consumers = 0      # live viewers attached to mjpeg_frames()

        self._picam.start()
        time.sleep(SETTLE_SECONDS)
        threading.Thread(target=self._capture_loop, daemon=True).start()

    @staticmethod
    def _orient(frame):
        code = _ROTATE_CODES.get(ROTATION)
        return cv2.rotate(frame, code) if code is not None else frame

    def _capture_loop(self):
        while self._running:
            with self._cam_lock:
                yuv = self._picam.capture_array("lores")
            gray = yuv[:_LORES_H, :_LORES_W]   # Y plane == grayscale, a free slice
            # The YUV->BGR conversion is the expensive part of this loop and only
            # the live stream needs colour, so skip it when nobody is watching.
            bgr = (self._orient(cv2.cvtColor(yuv, cv2.COLOR_YUV2BGR_I420))
                   if self._stream_consumers else None)
            with self._frame_lock:
                self._latest_gray = gray
                if bgr is not None:
                    self._latest_bgr = bgr
            time.sleep(1.0 / 30)

    # --- frame access (motion + live view) ---
    def latest_gray(self):
        with self._frame_lock:
            return None if self._latest_gray is None else self._latest_gray.copy()

    def latest_bgr(self):
        with self._frame_lock:
            return None if self._latest_bgr is None else self._latest_bgr.copy()

    def mjpeg_frames(self):
        """Yield JPEG bytes for a multipart/x-mixed-replace live stream."""
        interval = 1.0 / STREAM_FPS
        with self._frame_lock:
            self._stream_consumers += 1
        try:
            while True:
                frame = self.latest_bgr()
                if frame is not None:
                    ok, jpg = cv2.imencode(
                        ".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, STREAM_QUALITY])
                    if ok:
                        yield jpg.tobytes()
                time.sleep(interval)
        finally:
            with self._frame_lock:
                self._stream_consumers -= 1
                if self._stream_consumers <= 0:
                    self._stream_consumers = 0
                    self._latest_bgr = None   # don't serve a stale frame later

    # --- capture (photo + video) ---
    def capture_photo(self, path):
        """High-res still from the main stream."""
        with self._cam_lock:
            frame = self._picam.capture_array("main")
        # picamera2's "RGB888" hands back BGR-ordered bytes, which is already what
        # imwrite expects. The RGB2BGR conversion that used to be here swapped two
        # channels that were correct, which is why saved photos came out magenta.
        cv2.imwrite(path, self._orient(frame))
        return path

    def capture_full_photo(self, path):
        """Full-sensor still (2592x1944 on the OV5647), not the 1080p video main.

        switch_mode_and_capture_array drops into a still config for one frame and
        restores the video config, so the lores loop just waits on the lock. It
        can't happen mid-recording: the encoder owns the video config then.
        """
        if self._recording:
            raise RuntimeError("camera is recording; try again when it stops")
        with self._cam_lock:
            cfg = self._picam.create_still_configuration(
                main={"size": self._picam.sensor_resolution, "format": "RGB888"})
            frame = self._picam.switch_mode_and_capture_array(cfg, "main")
        cv2.imwrite(path, self._orient(frame), [cv2.IMWRITE_JPEG_QUALITY, 95])
        return path

    def start_recording(self, path):
        """Begin recording the main stream straight to mp4 (no temp .h264 + ffmpeg)."""
        if self._recording:
            return False
        with self._cam_lock:
            self._picam.start_encoder(H264Encoder(), FfmpegOutput(path))
        self._recording = True
        self._rec_path = path
        return True

    def stop_recording(self):
        if not self._recording:
            return False
        with self._cam_lock:
            self._picam.stop_encoder()
        self._recording = False
        return True

    def record_video(self, path, seconds):
        """Fixed-length recording (used by motion capture)."""
        if not self.start_recording(path):
            return None
        time.sleep(seconds)
        self.stop_recording()
        return path

    @property
    def recording(self):
        return self._recording

    @property
    def rec_path(self):
        """Path of the recording in progress, or the last one finished."""
        return self._rec_path

    @property
    def stream_consumers(self):
        return self._stream_consumers

    def close(self):
        self._running = False
        time.sleep(0.2)
        with self._cam_lock:
            self._picam.stop()
            self._picam.close()


def _load_tuning():
    """NoIR tuning if it's on this box, stock tuning otherwise."""
    try:
        return Picamera2.load_tuning_file(TUNING_FILE)
    except Exception:
        return None


_camera = None
_get_lock = threading.Lock()


def get_camera():
    """Return the process-wide Camera, creating it on first use."""
    global _camera
    with _get_lock:
        if _camera is None:
            _camera = Camera()
    return _camera
