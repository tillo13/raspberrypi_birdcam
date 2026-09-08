# Bird Cam

**What it is** — a self-hosted bird-watching camera that runs on a Raspberry Pi. It
watches a feeder or window, catches motion, saves the moment, and gives you a live
view and controls from any browser on your network.

**What it strives to do** — turn a Pi, a camera, and a Sense HAT into a tiny always-on
nature station: reliable motion capture with as few false triggers as possible,
light enough to run 24/7 on a Pi 3, and simple enough to check from your phone on the
couch.

## Features
- **Live view** — a smooth MJPEG stream straight into the browser.
- **Motion capture** — MOG2 background subtraction with tunable sensitivity, minimum
  area, cooldown, and consecutive-frame confirmation; saves a still on each trigger.
- **Manual photo & video** — one-tap capture and recording (video written to mp4).
- **Sense HAT** — temperature / humidity / pressure logging and an 8x8 LED-matrix
  display for countdowns and status.
- **Web control panel** — start/stop motion, tune settings, and browse captures from
  `http://<pi>:5000`.

## Hardware
- Raspberry Pi (developed on a Pi 3, Raspberry Pi OS **Bookworm**, 32-bit)
- Raspberry Pi Camera Module
- Sense HAT

## How it works
- **Camera** (`utilities/camera.py`) — one persistent `picamera2` camera. A single
  background thread pulls low-res frames that motion detection and the live stream
  share, while photos and video pull from the high-res stream. No per-frame subprocess.
- **Motion** (`utilities/motion.py`) — MOG2 background subtraction, which tolerates
  gradual outdoor light changes (clouds, dawn) far better than frame differencing.
- **Live view** — an MJPEG stream at `/api/stream`, rendered straight into an `<img>`.
- **Sensors / LED** (`utilities/sensehat_utils.py`) — Sense HAT readings + matrix output.
- **Web / API** (`app.py`) — Flask app + JSON API, served by **waitress** on port 5000.

## Setup
```bash
# System packages (Raspberry Pi OS Bookworm)
sudo apt install -y python3-picamera2 python3-opencv sense-hat python3-waitress ffmpeg

python app.py            # serves on http://0.0.0.0:5000
```

### Run as a service
```bash
sudo cp birdcam.service /etc/systemd/system/
sudo systemctl enable --now birdcam
```

## API
`/api/stream` (MJPEG) · `/api/take_photo` · `/api/start_recording` · `/api/stop_recording`
· `/api/start_motion` · `/api/stop_motion` · `/api/motion_status` · `/api/motion_settings`
· `/api/list_files` · `/api/counts` · `/api/latest_image` · `/files/<name>`

## Layout
```
app.py                      Flask app + JSON API + MJPEG stream (waitress)
config.py                   paths, port, motion/display defaults
utilities/camera.py         persistent picamera2 camera (frames, photo, video, stream)
utilities/motion.py         MOG2 motion detection
utilities/sensehat_utils.py Sense HAT sensors + LED matrix
templates/index.html        web UI
static/                     css + js
birdcam.service             systemd unit
```

## Ideas
- Optional on-device classification to tell birds from a swaying branch.
