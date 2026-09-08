#!/usr/bin/env python3
"""Bird Cam web app — Flask UI + JSON API + MJPEG live stream.

State lives on one BirdCam controller (camera, motion detector, Sense HAT display)
instead of scattered module globals, and the app is built by create_app() so
importing this file has no hardware side effects.
"""
import logging
import os
import threading
import time
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

from flask import Flask, Response, jsonify, render_template, request, send_from_directory

import config
from utilities import camera, motion, sensehat_utils


class BirdCam:
    """Owns the camera, motion detector, and Sense HAT display."""

    def __init__(self):
        config.MEDIA_DIR.mkdir(exist_ok=True)
        self.camera = camera.get_camera()
        self.motion = motion.MotionDetector()
        self.last_motion_capture = None
        self.last_motion_time = 0.0
        self._rec_name = None
        self._last_random = 0.0
        self._display_on = True
        sensehat_utils.clear_display()
        sensehat_utils.show_startup_message()
        threading.Thread(target=self._display_loop, daemon=True).start()

    def _display_loop(self):
        while self._display_on:
            try:
                if not self.camera.recording and not self.motion.active:
                    if time.time() - self._last_random > config.RANDOM_DISPLAY_INTERVAL:
                        sensehat_utils.show_random_display()
                        self._last_random = time.time()
                    sensehat_utils.always_on_display()
            except Exception:
                pass
            time.sleep(5)

    def _media_path(self, suffix):
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        return str(config.MEDIA_DIR / f"{ts}{suffix}")

    def take_photo(self):
        sensehat_utils.photo_countdown()
        name = Path(self.camera.capture_photo(self._media_path(".jpg"))).name
        sensehat_utils.show_photo_success()
        return name

    def start_recording(self):
        if not self.camera.start_recording(self._media_path(".mp4")):
            return None
        sensehat_utils.show_recording_active()
        self._rec_name = None
        return True

    def stop_recording(self):
        if not self.camera.stop_recording():
            return None
        sensehat_utils.show_recording_success()
        return self.list_files()[0] if self.list_files() else None

    def start_motion(self):
        if self.motion.start(self._on_motion):
            sensehat_utils.show_recording_active()
            return True
        return False

    def stop_motion(self):
        if self.motion.stop():
            sensehat_utils.clear_display()
            return True
        return False

    def _on_motion(self):
        name = Path(self.camera.capture_photo(self._media_path("_motion.jpg"))).name
        self.last_motion_capture = name
        self.last_motion_time = time.time()

    def _media_files(self):
        if not config.MEDIA_DIR.exists():
            return []
        return os.listdir(config.MEDIA_DIR)

    def counts(self):
        files = self._media_files()
        return {
            "photo_count": sum(1 for f in files if f.endswith(".jpg")),
            "video_count": sum(1 for f in files if f.endswith((".mp4", ".h264"))),
            "motion_count": sum(1 for f in files if "_motion" in f),
        }

    def list_files(self):
        files = [f for f in self._media_files() if f.endswith((".jpg", ".mp4", ".h264"))]
        return sorted(files, reverse=True)[:30]

    def latest_image(self):
        imgs = [f for f in self._media_files() if f.endswith(".jpg")]
        if not imgs:
            return None
        imgs.sort(key=lambda f: os.path.getmtime(config.MEDIA_DIR / f), reverse=True)
        return imgs[0]


def _setup_logging(app):
    config.LOG_DIR.mkdir(exist_ok=True)
    fh = RotatingFileHandler(config.LOG_DIR / "birdcam.log",
                             maxBytes=10 * 1024 * 1024, backupCount=10)
    fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s: %(message)s"))
    app.logger.addHandler(fh)
    app.logger.addHandler(logging.StreamHandler())
    app.logger.setLevel(logging.INFO)


def create_app(bc=None):
    app = Flask(__name__)
    _setup_logging(app)
    bc = bc or BirdCam()
    app.logger.info("Bird Cam startup")

    @app.route("/")
    def index():
        return render_template("index.html")

    @app.route("/api/stream")
    def stream():
        def frames():
            sensehat_utils.start_live_mode()
            try:
                for jpg in bc.camera.mjpeg_frames():
                    yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpg + b"\r\n"
            finally:
                sensehat_utils.stop_live_mode()
        return Response(frames(),
                        mimetype="multipart/x-mixed-replace; boundary=frame")

    @app.route("/api/take_photo", methods=["POST"])
    def take_photo():
        try:
            return jsonify(success=True, message="Photo saved!", filename=bc.take_photo())
        except Exception as e:
            sensehat_utils.show_photo_error()
            app.logger.error("take_photo: %s", e)
            return jsonify(success=False, message=str(e))

    @app.route("/api/start_recording", methods=["POST"])
    def start_recording():
        if bc.start_recording():
            return jsonify(success=True, message="Recording started")
        return jsonify(success=False, message="Already recording")

    @app.route("/api/stop_recording", methods=["POST"])
    def stop_recording():
        name = bc.stop_recording()
        if name is None:
            return jsonify(success=False, message="Not recording")
        return jsonify(success=True, message="Video saved!", filename=name)

    @app.route("/api/start_motion", methods=["POST"])
    def start_motion():
        if bc.start_motion():
            return jsonify(success=True, message="Motion detection started")
        return jsonify(success=False, message="Motion detection already active")

    @app.route("/api/stop_motion", methods=["POST"])
    def stop_motion():
        if bc.stop_motion():
            return jsonify(success=True, message="Motion detection stopped")
        return jsonify(success=False, message="Motion detection not active")

    @app.route("/api/motion_status")
    def motion_status():
        return jsonify(success=True, is_active=bc.motion.active,
                       last_capture=bc.last_motion_capture,
                       last_capture_time=bc.last_motion_time)

    @app.route("/api/motion_settings", methods=["GET", "POST"])
    def motion_settings():
        if request.method == "GET":
            return jsonify(success=True, **bc.motion.get_settings())
        d = request.json or {}
        settings = bc.motion.update_settings(
            threshold=d.get("threshold"), min_area=d.get("min_area"),
            cooldown=d.get("cooldown"), consecutive_frames=d.get("consecutive_frames"))
        return jsonify(success=True, **settings)

    @app.route("/api/list_files")
    def list_files():
        return jsonify(success=True, files=bc.list_files())

    @app.route("/api/counts")
    def counts():
        return jsonify(bc.counts())

    @app.route("/api/latest_image")
    def latest_image():
        name = bc.latest_image()
        if name is None:
            return jsonify(success=False, message="No images found")
        return jsonify(success=True, image=name, url=f"/files/{name}")

    @app.route("/api/stop_live_mode", methods=["POST"])
    def stop_live_mode():
        sensehat_utils.stop_live_mode()
        return jsonify(success=True)

    @app.route("/api/test_countdown", methods=["POST"])
    def test_countdown():
        sensehat_utils.photo_countdown()
        sensehat_utils.clear_display()
        return jsonify(success=True, message="Countdown test complete")

    @app.route("/api/force_random_display", methods=["POST"])
    def force_random_display():
        sensehat_utils.show_random_display()
        return jsonify(success=True, message="Random display shown")

    @app.route("/files/<path:filename>")
    def serve_file(filename):
        return send_from_directory(config.MEDIA_DIR, filename)

    return app


if __name__ == "__main__":
    from waitress import serve
    application = create_app()
    print(f"🦜 Bird Cam ready at http://{config.HOST}:{config.PORT}")
    serve(application, host=config.HOST, port=config.PORT, threads=8)
