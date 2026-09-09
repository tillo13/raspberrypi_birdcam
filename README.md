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
  area, cooldown, and consecutive-frame confirmation. Each trigger saves a still, and
  the first trigger of a visit also records a short clip of what happened next.
- **Bird visits** — captures are clustered into visits by their timestamps, so the page
  shows events ("07:14, 3 triggers, 30s") instead of a wall of filenames, plus a
  by-the-hour activity histogram for the day.
- **Conditions** — Sense HAT temperature / humidity / pressure on the dashboard and
  stamped onto every visit, so you can ask when birds actually turn up.
- **Manual photo & video** — one-tap capture and recording (video written to mp4).
- **Timelapse** — assemble a day's stills into a clip with ffmpeg, in the background.
- **Sense HAT LED matrix** — countdowns, status animations, and scrolling text.
- **Web control panel** — start/stop motion, tune settings, and browse captures from
  `http://<pi>:5000`. Dark mode follows the system theme, with a manual toggle.

## Hardware
- Raspberry Pi (developed on a Pi 3, Raspberry Pi OS **Bookworm**, 32-bit)
- **Raspberry Pi Camera Module v1 — NoIR (`ov5647`)**
- Sense HAT

> **Two camera assumptions are baked into `utilities/camera.py`.** Both are one-line
> changes at the top of that file, and both will look like bugs if your setup differs:
> - `TUNING_FILE = "ov5647_noir.json"` — the NoIR module has no IR-cut filter, so it
>   needs the greyworld tuning. On a *filtered* module, set this to `ov5647.json`.
> - `ROTATION = 90` — corrects a module mounted a quarter-turn off. Set to `0` if yours
>   is mounted straight.
>
> A NoIR camera renders sunlit foliage magenta no matter what the software does:
> chlorophyll is a strong near-infrared reflector, and infrared lands in the red channel.
> The tuning compensates; only a physical IR-cut filter removes it. That trade buys you
> dawn and dusk, which is when the birds actually show up.

## How it works
- **Camera** (`utilities/camera.py`) — one persistent `picamera2` camera. A single
  background thread pulls low-res frames that motion detection and the live stream
  share, while photos and video pull from the high-res stream. No per-frame subprocess.
  The YUV→BGR conversion only runs while someone is watching the stream, and stills and
  the live view are rotated to correct the mounting angle (recorded clips are not —
  `FfmpegOutput` takes no extra ffmpeg args).
- **Motion** (`utilities/motion.py`) — MOG2 background subtraction, which tolerates
  gradual outdoor light changes (clouds, dawn) far better than frame differencing.
- **Visits** (`utilities/visits.py`) — groups motion captures into events by filename
  timestamp, and joins the conditions logged at trigger time from `logs/motion_events.jsonl`.
- **Conditions** (`utilities/weather.py`) — Sense HAT readings, corrected for the Pi's
  own heat. The board sits in the CPU's exhaust and reads hot, so a share of the
  CPU/sensor gap is subtracted; `CPU_HEAT_FACTOR` needs calibrating per enclosure, and
  raw values ride along in the response so the correction stays auditable.
- **Timelapse** (`utilities/timelapse.py`) — ffmpeg on a worker thread; the UI polls for
  status. Frame count is capped so a Pi 3 encode stays bounded.
- **Live view** — an MJPEG stream at `/api/stream`, rendered straight into an `<img>`.
- **Sensors / LED** (`utilities/sensehat_utils.py`) — Sense HAT readings + matrix output.
  Scrolling text is serialised on a worker so it never blocks a web request.
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

Camera init takes roughly 15 seconds under systemd — poll for readiness rather than
assuming the port is up.

## API
**Capture** `/api/take_photo` · `/api/start_recording` · `/api/stop_recording`
**Live** `/api/stream` (MJPEG) · `/api/stop_live_mode`
**Motion** `/api/start_motion` · `/api/stop_motion` · `/api/motion_status` · `/api/motion_settings`
**Visits & media** `/api/visits` · `/api/list_files` · `/api/counts` · `/api/latest_image` · `/files/<name>`
**Conditions** `/api/weather`
**Timelapse** `/api/timelapse` (POST) · `/api/timelapse_status`
**Sense HAT** `/api/say` (POST) · `/api/test_countdown` · `/api/force_random_display`

## Layout
```
app.py                      Flask app + JSON API + MJPEG stream (waitress)
config.py                   paths, port, motion/visit/weather/timelapse defaults
utilities/camera.py         persistent picamera2 camera (frames, photo, video, stream)
utilities/motion.py         MOG2 motion detection
utilities/visits.py         motion captures -> visits + hourly histogram
utilities/weather.py        Sense HAT conditions, corrected for CPU heat
utilities/timelapse.py      background ffmpeg timelapse builder
utilities/sensehat_utils.py Sense HAT sensors + LED matrix + scrolling text
templates/index.html        web UI
static/css/                 style.css (tokens, dark mode) + motion.css
static/js/                  birds.js, motion.js, weather.js, visits.js
birdcam.service             systemd unit
```

## Ideas
- **Name what it saw.** A capture can be described by a vision model and the word
  scrolled across the LED matrix. Proven end-to-end; the design constraint is to describe
  once per *visit*, off-thread — a describe takes several seconds and motion fires far
  more often than birds arrive.
- **Day/night profiles.** Short exposure and low gain by day; long exposure, high gain,
  lower framerate and looser motion thresholds after dark, driven by sun elevation rather
  than scene classification. The NoIR sensor is an advantage here, not a liability.
- **Manual `ColourGains`** instead of greyworld. Greyworld flattens scenes dominated by a
  single hue (an all-green hedge goes grey); a locked daylight white balance may avoid both
  the magenta and the flatness.
