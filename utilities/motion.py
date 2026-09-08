"""Motion detection via MOG2 background subtraction.

Replaces the old "diff against one reference frame" approach: MOG2 models the
background statistically, so gradual light changes (clouds, dawn) stop tripping it
— which is what an outdoor bird cam lives in. Frames come from the shared camera,
so there is no per-frame subprocess and no camera_busy flag.
"""
import threading
import time

import cv2

from utilities import camera as camera_mod

DEFAULTS = {
    "threshold": 25,          # MOG2 varThreshold — higher = less sensitive
    "min_area": 400,          # min changed-area (px) to count as motion
    "cooldown": 2.0,          # seconds between triggers
    "consecutive_frames": 2,  # frames of motion in a row before firing
}
SAMPLE_INTERVAL = 0.1   # ~10 samples/sec
WARMUP_FRAMES = 15      # let MOG2 learn the scene before it can trigger


class MotionDetector:
    def __init__(self):
        self._settings = dict(DEFAULTS)
        self._lock = threading.Lock()
        self._active = False
        self._on_motion = None
        self._last_trigger = 0.0

    def start(self, on_motion):
        with self._lock:
            if self._active:
                return False
            self._active = True
            self._on_motion = on_motion
        threading.Thread(target=self._loop, daemon=True).start()
        return True

    def stop(self):
        with self._lock:
            was = self._active
            self._active = False
        return was

    @property
    def active(self):
        return self._active

    def get_settings(self):
        with self._lock:
            return {**self._settings, "is_active": self._active}

    def update_settings(self, threshold=None, min_area=None, cooldown=None,
                        consecutive_frames=None):
        with self._lock:
            if threshold is not None:
                self._settings["threshold"] = int(threshold)
            if min_area is not None:
                self._settings["min_area"] = int(min_area)
            if cooldown is not None:
                self._settings["cooldown"] = float(cooldown)
            if consecutive_frames is not None:
                self._settings["consecutive_frames"] = int(consecutive_frames)
            return {**self._settings, "is_active": self._active}

    def _loop(self):
        cam = camera_mod.get_camera()
        bg = cv2.createBackgroundSubtractorMOG2(
            history=300, varThreshold=self._settings["threshold"], detectShadows=False)
        streak = 0
        seen = 0
        while self._active:
            time.sleep(SAMPLE_INTERVAL)
            gray = cam.latest_gray()
            if gray is None:
                continue
            with self._lock:
                s = dict(self._settings)
            bg.setVarThreshold(s["threshold"])
            mask = cv2.medianBlur(bg.apply(gray), 5)
            seen += 1
            if seen <= WARMUP_FRAMES:            # model still learning the scene
                continue
            contours, _ = cv2.findContours(
                mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            moved = any(cv2.contourArea(c) >= s["min_area"] for c in contours)
            streak = streak + 1 if moved else 0
            now = time.time()
            if (streak >= s["consecutive_frames"]
                    and now - self._last_trigger >= s["cooldown"]):
                self._last_trigger = now
                streak = 0
                if self._on_motion:
                    try:
                        self._on_motion()
                    except Exception:
                        pass
