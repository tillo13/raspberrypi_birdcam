# Bird Cam

A self-hosted bird-watching camera for the Raspberry Pi. It watches a feeder or a window,
catches motion, saves the moment, and gives you a live view, controls, and a one-call
photo API from any browser on your home network.

The goal: turn a Pi, a camera, and a Sense HAT into a tiny always-on nature station.
Reliable motion capture with few false triggers, light enough to run 24/7 on a Pi 3, and
simple enough to check from your phone on the couch.

Once a year it moonlights as a haunted walkway; see [Halloween ghost mode](#halloween-ghost-mode-seasonal).

## Quick start
```bash
# Raspberry Pi OS Bookworm
sudo apt install -y python3-picamera2 python3-opencv sense-hat python3-waitress ffmpeg v4l-utils
python app.py                       # http://<pi>:5000

curl -o bird.jpg http://<pi>:5000/api/snap/noir   # grab a photo from any machine on the LAN
```

## Features
- **Live view**: a smooth MJPEG stream straight into the browser.
- **Motion capture**: MOG2 background subtraction with tunable sensitivity, minimum area,
  cooldown, and consecutive-frame confirmation. Each trigger saves a still, and the first
  trigger of a visit also records a short clip of what happened next.
- **Bird visits**: captures are clustered into visits by timestamp, so the page shows events
  ("07:14, 3 triggers, 30s") instead of a wall of filenames, plus an activity-by-hour
  histogram for the day.
- **Conditions**: Sense HAT temperature, humidity, and pressure on the dashboard, stamped onto
  every visit, so you can ask when birds actually turn up.
- **Snapshot API**: any machine on your LAN grabs a photo from either camera with one GET.
  Fast by default, biggest-possible on request.
- **Second camera, plug and play**: add any USB webcam; the API notices when it is plugged in
  or pulled out.
- **Manual photo and video**: one-tap capture and recording (mp4).
- **Timelapse**: a day's stills assembled into a clip with ffmpeg, in the background.
- **Sense HAT LED matrix**: countdowns, status animations, and scrolling text.
- **Web control panel** at `http://<pi>:5000`: start and stop motion, tune settings, browse
  captures. Dark mode follows the system, with a manual toggle.

## Snapshot API
Take a photo from a browser tab or `curl`, from any machine on the home network.

```bash
curl http://<pi>:5000/api/snap                              # menu: cameras, modes, what's plugged in
curl -o bird.jpg http://<pi>:5000/api/snap/usb               # fast (the default)
curl -o bird.jpg "http://<pi>:5000/api/snap/noir?mode=max"   # biggest still
```

| camera | `fast` (default) | `max` |
|---|---|---|
| `noir` (Pi camera) | 1080p frame from the live stream, ~1 s | full sensor, 2592x1944, ~2.4 s |
| `usb` (webcam) | newest frame of a running 1080p stream, ~0.2 s | the webcam's largest mode (C922: 2304x1536), 11 to 19 s |

*Timings measured on a Pi 3 over Wi-Fi, 2026-10-22.*

**Why fast is the default.** A bird is gone in a second. Opening a webcam cold costs 2 to 5 s
before the first frame (as of 2026-10-22 on a Pi 3: ffmpeg start 1.9 s, first 2304x1536 frame
5.1 s), so the webcam is kept streaming at 1080p 15 fps and a snap hands back its newest frame.
Webcams JPEG-encode their MJPEG frames themselves, so holding them costs no decode.

**Unplugging the webcam is fine.** The menu's `cameras.usb.available` is a live check, and a
snap from a missing webcam fails at once with a 503 and `"available": false`. Plug it back in
and the stream restarts on its own within a few seconds.

**Getting a photo again later.** The response body is the JPEG. Every snap is also saved as
`media/<timestamp>_snap_<cam>[_max].jpg`; the `X-Snap-File` and `X-Snap-Url` response headers
point at the saved copy, which `/files/<name>` serves and `/api/list_files` lists.

**Who can call it.** Only addresses in `SNAP_NETWORKS` at the top of `app.py` (default
`10.0.0.0/24` plus the Pi itself) get a photo; anyone else gets a 403. Set it to your LAN's
range. It is a GET on purpose so a browser tab works. The rest of the app has no login, so keep
port 5000 off the internet.

**Errors.** 404 unknown camera, 400 unknown mode (the body lists the valid ones), 503 camera
unavailable (webcam unplugged, or `noir` `max` while a motion clip is recording).

**Focus.** The webcam runs continuous autofocus, which happily locks onto a window screen a few
inches away instead of the yard. Remove the screen, or pin focus far with
`v4l2-ctl -c focus_automatic_continuous=0 -c focus_absolute=0` (resets when replugged).

## Hardware
- Raspberry Pi (developed on a Pi 3, Raspberry Pi OS **Bookworm**, 32-bit)
- **Raspberry Pi Camera Module v1, NoIR (`ov5647`)**
- Sense HAT
- Optional: any USB (UVC) webcam, tested with a Logitech C922 Pro Stream. It is found by USB
  bus, so nothing in the config names the model.
- A real 2.5 A power supply. A Pi 3 on a computer's USB port reports under-voltage, and a
  webcam adds to the draw.

> **Two camera assumptions live at the top of `utilities/camera.py`.** Both are one-line
> changes, and both look like bugs if your setup differs:
> - `TUNING_FILE = "ov5647_noir.json"`: the NoIR module has no IR-cut filter, so it needs the
>   greyworld tuning. On a *filtered* module, set this to `ov5647.json`.
> - `ROTATION = 90`: corrects a module mounted a quarter-turn off. Set it to `0` if yours is
>   mounted straight.
>
> A NoIR camera renders sunlit foliage magenta no matter what the software does: chlorophyll
> reflects near-infrared strongly, and infrared lands in the red channel. The tuning
> compensates; only a physical IR-cut filter removes it. The trade buys you dawn and dusk,
> which is when the birds show up, and night vision with an IR light.

## How it works
- **Camera** (`utilities/camera.py`): one persistent `picamera2` camera. A single background
  thread pulls low-res frames that motion detection and the live stream share, while photos
  and video use the high-res stream. The YUV to BGR conversion only runs while someone is
  watching, and stills and the live view are rotated to fix the mounting angle (recorded clips
  are not, because `FfmpegOutput` takes no extra ffmpeg args). A `max` snap switches to the
  full-sensor still mode for one frame and back.
- **Webcam** (`utilities/usb_camera.py`): a background ffmpeg holds the webcam open as a 1080p
  MJPEG stream and the newest frame is kept in memory. `max` pauses it, captures the largest
  mode the device advertises, and resumes. Unplug and replug are handled by the same loop.
- **Motion** (`utilities/motion.py`): MOG2 background subtraction, which copes with gradual
  outdoor light changes (clouds, dawn) far better than frame differencing.
- **Visits** (`utilities/visits.py`): groups motion captures into events by filename timestamp
  and joins the conditions logged at trigger time from `logs/motion_events.jsonl`.
- **Conditions** (`utilities/weather.py`): Sense HAT readings corrected for the Pi's own heat.
  The board sits in the CPU's exhaust and reads hot, so a share of the CPU/sensor gap is
  subtracted; `CPU_HEAT_FACTOR` needs calibrating per enclosure, and the raw values ride along
  in the response so the correction stays auditable.
- **Timelapse** (`utilities/timelapse.py`): ffmpeg on a worker thread; the UI polls for status.
  The frame count is capped so a Pi 3 encode stays bounded.
- **Sense HAT** (`utilities/sensehat_utils.py`): sensor readings and matrix output. Scrolling
  text runs on a worker so it never blocks a web request.
- **Web and API** (`app.py`): Flask, served by **waitress** on port 5000. Cross-site
  form posts are refused (`utilities/csrf_guard.py`).

## Run as a service
```bash
sudo cp birdcam.service /etc/systemd/system/
sudo systemctl enable --now birdcam
```
Camera start-up takes roughly 15 to 20 seconds under systemd, so poll for readiness rather than
assuming the port is up.

## API
| area | endpoints |
|---|---|
| Snapshot | `/api/snap` (menu) · `/api/snap/<noir\|usb>?mode=<fast\|max>` |
| Capture | `/api/take_photo` · `/api/start_recording` · `/api/stop_recording` |
| Live | `/api/stream` (MJPEG) · `/api/stop_live_mode` |
| Motion | `/api/start_motion` · `/api/stop_motion` · `/api/motion_status` · `/api/motion_settings` |
| Visits and media | `/api/visits` · `/api/list_files` · `/api/counts` · `/api/latest_image` · `/files/<name>` |
| Conditions | `/api/weather` |
| Timelapse | `/api/timelapse` (POST) · `/api/timelapse_status` |
| Sense HAT | `/api/say` (POST) · `/api/test_countdown` · `/api/force_random_display` |

## Layout
```
app.py                      Flask app, JSON API, MJPEG stream, snapshot API (waitress)
config.py                   paths, port, motion / visit / weather / timelapse defaults
utilities/camera.py         persistent picamera2 camera (frames, photo, full-sensor still, video, stream)
utilities/usb_camera.py     USB webcam: always-on 1080p stream, largest-mode stills, plug detection
utilities/motion.py         MOG2 motion detection
utilities/visits.py         motion captures to visits, plus the hourly histogram
utilities/weather.py        Sense HAT conditions, corrected for CPU heat
utilities/timelapse.py      background ffmpeg timelapse builder
utilities/sensehat_utils.py Sense HAT sensors, LED matrix, scrolling text
utilities/csrf_guard.py     refuses cross-site form and API posts
templates/index.html        web UI
static/css/                 style.css (tokens, dark mode) and motion.css
static/js/                  birds.js, motion.js, weather.js, visits.js
birdcam.service             systemd unit
```

## Halloween ghost mode (seasonal)

For one week a year the bird feeder cam becomes a haunted walkway. Same Pi, same motion
detector, one extra reaction: when something walks up the path after dark, a ghost talks
to it through a Google Home Mini hidden near the door. Plan and status: kumori task #488
(party 2026-10-31). Wired 2026-10-31: `utilities/ghost.py`, settings under "Halloween ghost
mode" in `config.py` (hours, cooldown, speaker, volume).

```bash
curl http://<pi>:5000/api/haunt                      # armed? cooling? lines played, last error
curl http://<pi>:5000/api/haunt/play                 # fire the next line now (LAN only; a phone bookmark works)
curl "http://<pi>:5000/api/haunt/play?clip=08.mp3"   # a specific one
curl -X POST -H 'Content-Type: application/json' -d '{"on":false}' http://<pi>:5000/api/haunt/enabled   # off switch
curl -X POST -H 'Content-Type: application/json' -d '{"on":true,"all_day":true}' http://<pi>:5000/api/haunt/enabled   # test outside the hours (until restart)
python tools/render_ghost_pool.py lines.txt          # lines -> ghost/pool/NN.mp3 (Kokoro venv), then copy to the Pi
```

**How it hangs together**
- **Trigger**: `BirdCam._on_motion` in `app.py`, the same hook that saves a bird capture.
  Ghost mode adds a second listener; it never replaces the capture, so every trick-or-treater
  is also in the gallery the next morning.
- **Voice**: the Pi 3 is armv7 and cannot run a TTS model, so lines are rendered ahead of
  time on a bigger machine (Kokoro voice, slowed, then an ffmpeg echo chain for the
  "down a well" sound) and copied to `pool/*.wav` on the Pi. The lines and wavs are not in
  this repo; the ghost keeps its own secrets.
- **Speaker**: a repurposed Google Home Mini on the LAN, played through a Cast client. One
  clip per visitor, picked at random with no repeats until the pool is used up, then a
  45-60 s cooldown so one kid standing on the mat does not get a monologue.
- **Face**: the Sense HAT LED matrix. Motion scrolls `BOO`, and a nightly visitor count
  replaces the usual temperature once the sun is down.
- **Power**: both the Pi and the Mini currently hang off a PC's USB ports and the Pi reports
  under-voltage. Wall supplies before the party, or the ghost dies mid-sentence.

**Ideas, in rough order of effort**
- **Two-stage scare.** First motion at the gate gets a whisper ("I see you... coming up the
  walk"); motion at the door, 10 s later, gets the loud one. Two zones in the MOG2 mask, two
  pools.
- **Costume commentary.** Snap the visitor with `/api/snap/usb`, send it to a vision model,
  and have the ghost say one line about what it sees: "a very small dinosaur... how brave."
  This is the Name-what-it-saw idea below with a sheet over it. Off-thread, once per visit,
  with a canned fallback line when the model is slow.
- **Candy bowl guard.** A second cheap motion zone on the bowl itself. One hand, silence.
  A second grab inside 5 s: "the house is counting."
- **Visitor leaderboard.** The visits page already groups motion into events; add a
  Halloween view that counts groups per hour, biggest group, latest visitor, and the pool
  line each one got. Screenshot it for the group chat at midnight.
- **Ghost cam feed.** Mirror the live view to a TV in the window with a slow ghost overlay
  (CSS, no GPU needed) so the kids see themselves being watched on the way up.
- **Thunder on demand.** `/api/say` already exists for the matrix; a `/api/haunt/<clip>` route
  lets a phone on the couch fire any clip by hand when the automatic one misses.
- **Fog cue.** A smart plug on a fog machine toggled from the same hook, 3 s before the voice,
  so the line arrives out of the fog instead of before it.
- **Quiet hours and an off switch.** Ghost mode arms at dusk, disarms at 21:30, and the
  Sense HAT joystick press kills it instantly for the one kid who is genuinely scared.
- **Morning-after reel.** The timelapse worker can stitch every night capture into a 30 s
  clip at 7 a.m. The bird cam already knows how; it just needs a date filter.

## Ideas
- **Name what it saw.** A capture can be described by a vision model and the word scrolled
  across the LED matrix. Proven end to end; the design constraint is to describe once per
  *visit*, off-thread, because a describe takes several seconds and motion fires far more
  often than birds arrive.
- **Day and night profiles.** Short exposure and low gain by day; long exposure, high gain,
  a lower framerate and looser motion thresholds after dark, driven by sun elevation rather
  than scene classification. The NoIR sensor is an advantage here, not a liability.
- **Manual `ColourGains`** instead of greyworld. Greyworld flattens scenes dominated by one hue
  (an all-green hedge goes grey); a locked daylight white balance may avoid both the magenta
  and the flatness.
- **Pre-trigger buffer.** Keep the last few seconds of webcam frames so a motion capture can
  include the moment *before* the trigger, not just after.
