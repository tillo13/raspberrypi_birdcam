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

MAIN_SIZE = (1920, 1080)   # high-res: photos + video
LORES_SIZE = (640, 480)    # low-res: motion + live stream (Y plane is grayscale)
STREAM_FPS = 15            # cap for the live MJPEG stream
STREAM_QUALITY = 80        # JPEG quality for the live stream
SETTLE_SECONDS = 1.0       # let AE/AWB settle after start

_LORES_W, _LORES_H = LORES_SIZE


class Camera:
    def __init__(self):
        self._picam = Picamera2()
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

        self._picam.start()
        time.sleep(SETTLE_SECONDS)
        threading.Thread(target=self._capture_loop, daemon=True).start()

    def _capture_loop(self):
        while self._running:
            with self._cam_lock:
                yuv = self._picam.capture_array("lores")
            gray = yuv[:_LORES_H, :_LORES_W]                 # Y plane == grayscale
            bgr = cv2.cvtColor(yuv, cv2.COLOR_YUV2BGR_I420)  # colour for live view
            with self._frame_lock:
                self._latest_gray = gray
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
        while True:
            frame = self.latest_bgr()
            if frame is not None:
                ok, jpg = cv2.imencode(
                    ".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, STREAM_QUALITY])
                if ok:
                    yield jpg.tobytes()
            time.sleep(interval)

    # --- capture (photo + video) ---
    def capture_photo(self, path):
        """High-res still from the main stream."""
        with self._cam_lock:
            rgb = self._picam.capture_array("main")
        cv2.imwrite(path, cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))
        return path

    def start_recording(self, path):
        """Begin recording the main stream straight to mp4 (no temp .h264 + ffmpeg)."""
        if self._recording:
            return False
        with self._cam_lock:
            self._picam.start_encoder(H264Encoder(), FfmpegOutput(path))
        self._recording = True
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

    def close(self):
        self._running = False
        time.sleep(0.2)
        with self._cam_lock:
            self._picam.stop()
            self._picam.close()


_camera = None
_get_lock = threading.Lock()


def get_camera():
    """Return the process-wide Camera, creating it on first use."""
    global _camera
    with _get_lock:
        if _camera is None:
            _camera = Camera()
    return _camera
