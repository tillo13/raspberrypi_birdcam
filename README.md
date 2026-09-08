# Bird Cam

**What it is** — a self-hosted bird-watching camera that runs on a Raspberry Pi. It
watches a feeder or window, catches motion, saves the moment, and gives you a live
view and controls from any browser on your network.

**What it strives to do** — turn a Pi, a camera, and a Sense HAT into a tiny always-on
nature station: reliable motion capture with as few false triggers as possible,
light enough to run 24/7 on a Pi 3, and simple enough to check from your phone on the
couch. The near-term aim is to modernize the capture pipeline (picamera2), clean up
the paths, and pin dependencies so it's clone-and-run on a fresh Pi.

## Features
- **Live view** — on-demand snapshots from the Pi camera, straight in the browser.
- **Motion capture** — OpenCV frame-differencing with tunable threshold, minimum
  area, cooldown, and consecutive-frame confirmation; saves a still on each trigger.
- **Manual photo & video** — one-tap capture and timed recording.
- **Sense HAT** — temperature / humidity / pressure logging and an 8x8 LED-matrix
  display for countdowns and status.
- **Web control panel** — start/stop motion, tune settings, and browse captures from
  `http://<pi>:5000`.

## Hardware
- Raspberry Pi (developed on a Pi 3, Raspberry Pi OS **Bookworm**, 32-bit)
- Raspberry Pi Camera Module
- Sense HAT

## How it works
- **Camera:** frames captured by shelling out to `libcamera-still` / `libcamera-vid`.
- **Motion:** `utilities/motion_utils.py` — OpenCV diff against a rolling reference.
- **Sensors / LED:** `utilities/sensehat_utils.py` — Sense HAT readings + matrix output.
- **Web / API:** `app.py` — Flask, serves the UI and a small JSON API on port 5000.

## Setup
```bash
# System (Raspberry Pi OS Bookworm)
sudo apt install -y libcamera-apps python3-opencv sense-hat

# Python
pip install flask numpy

python app.py            # serves on http://0.0.0.0:5000
```

## API
`/api/live_snapshot` · `/api/take_photo` · `/api/start_recording` · `/api/stop_recording`
· `/api/start_motion` · `/api/stop_motion` · `/api/motion_status` · `/api/motion_settings`
· `/api/list_files` · `/api/counts` · `/api/latest_image` · `/files/<name>`

## Layout
```
app.py                      Flask app + API
utilities/motion_utils.py   camera capture + OpenCV motion detection
utilities/sensehat_utils.py Sense HAT sensors + LED matrix
templates/index.html        web UI
static/                     css + js
test_*.py                   hardware sanity checks (motion, orientation, sensehat)
```

## Roadmap
- Camera pipeline off the `libcamera-*` CLI → in-process **picamera2** (or Bookworm's
  `rpicam-*` tools).
- Cleaner paths, a pinned `requirements.txt`, and a systemd unit for boot-time start.
