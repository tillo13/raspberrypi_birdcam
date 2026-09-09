"""Central configuration for Bird Cam."""
from pathlib import Path

BASE_DIR = Path(__file__).parent
MEDIA_DIR = BASE_DIR / "media"
LOG_DIR = BASE_DIR / "logs"

HOST = "0.0.0.0"
PORT = 5000

MOTION_RECORD_SECONDS = 10      # length of a motion-triggered clip
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
