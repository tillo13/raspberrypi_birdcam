"""Central configuration for Bird Cam."""
from pathlib import Path

BASE_DIR = Path(__file__).parent
MEDIA_DIR = BASE_DIR / "media"
LOG_DIR = BASE_DIR / "logs"

HOST = "0.0.0.0"
PORT = 5000

MOTION_RECORD_SECONDS = 10      # length of a motion-triggered clip
MOTION_CAMERA = "usb"           # which camera motion watches: "noir" (ribbon, sees in low light) or "usb" (webcam)
RANDOM_DISPLAY_INTERVAL = 300   # seconds between Sense HAT idle animations

# --- Visits (motion captures grouped into bird visits) ---
VISIT_GAP_SECONDS = 90          # a gap longer than this starts a new visit
VISIT_LIMIT = 40                # most recent visits returned to the UI
EVENTS_LOG = LOG_DIR / "motion_events.jsonl"

# --- Sense HAT ambient readings ---
WEATHER_CACHE_SECONDS = 20      # don't re-read i2c more often than this
CPU_HEAT_FACTOR = 1.5           # divisor on the CPU/sensor gap; calibrate per enclosure

# --- Timelapse ---
TIMELAPSE_FPS = 12
TIMELAPSE_WIDTH = 1280
TIMELAPSE_MAX_FRAMES = 600      # ~50s of output at 12fps; bounds Pi 3 encode time

# --- Halloween ghost mode (utilities/ghost.py) ---
GHOST_ENABLED = True            # also starts motion detection at boot, so a reboot re-arms it
GHOST_HOURS = (0, 24)           # local hours it may talk; (0, 24) = whenever it is plugged in (Andy, 2026-10-31)
GHOST_COOLDOWN_SECONDS = 0      # extra quiet after a line finishes; 0 = next line as soon as one ends (Andy, 2026-10-31)
GHOST_POOL_DIR = BASE_DIR / "ghost" / "pool"
GHOST_SPEAKER_NAME = "Goodwin room speaker"
GHOST_SPEAKER_IP = "10.0.0.219"
GHOST_SPEAKER_UUID = "5b3cdfa1-ea7d-79a1-ed08-cc76d500f7bc"
GHOST_VOLUME = 0.8
