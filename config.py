"""Central configuration for Bird Cam."""
from pathlib import Path

BASE_DIR = Path(__file__).parent
MEDIA_DIR = BASE_DIR / "media"
LOG_DIR = BASE_DIR / "logs"

HOST = "0.0.0.0"
PORT = 5000

MOTION_RECORD_SECONDS = 10      # length of a motion-triggered clip
RANDOM_DISPLAY_INTERVAL = 300   # seconds between Sense HAT idle animations
