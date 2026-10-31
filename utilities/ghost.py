"""Halloween ghost mode: motion on the walk -> one spooky line on a Google Cast speaker.

Clips are pre-rendered elsewhere (tools/render_ghost_pool.py; the Pi 3 can't run TTS) and live
in ghost/pool/*.mp3, served by the app at /ghost/<name> so the speaker can fetch them.
One line per visitor: a shuffled bag (no repeat until all have played), then a cooldown.
"""
import logging
import random
import socket
import threading
import time
from datetime import datetime

import config

log = logging.getLogger(__name__)


def _my_ip():
    """The address the speaker can reach us on (the LAN interface, not 127.0.0.1)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect((config.GHOST_SPEAKER_IP, 8009))
        return s.getsockname()[0]
    finally:
        s.close()


class Ghost:
    def __init__(self):
        self._lock = threading.Lock()
        self._cast = None
        self._bag = []
        self.last_played = 0.0
        self.last_clip = None
        self.played_tonight = 0
        self.last_error = None
        self.enabled = config.GHOST_ENABLED
        self.all_day = False  # test switch: ignore GHOST_HOURS until the app restarts

    def clips(self):
        if not config.GHOST_POOL_DIR.exists():
            return []
        return sorted(p.name for p in config.GHOST_POOL_DIR.glob("*.mp3"))

    def in_hours(self, now=None):
        start, end = config.GHOST_HOURS
        return start <= (now or datetime.now()).hour < end

    def armed(self):
        return self.enabled and (self.all_day or self.in_hours()) and bool(self.clips())

    def cooling(self):
        return time.time() - self.last_played < config.GHOST_COOLDOWN_SECONDS

    def _next_clip(self):
        if not self._bag:
            self._bag = self.clips()
            random.shuffle(self._bag)
            # never the same line twice in a row across a reshuffle
            if len(self._bag) > 1 and self._bag[-1] == self.last_clip:
                self._bag.insert(0, self._bag.pop())
        return self._bag.pop()

    def _speaker(self):
        if self._cast is None:
            import pychromecast
            casts, browser = pychromecast.get_listed_chromecasts(
                friendly_names=[config.GHOST_SPEAKER_NAME],
                known_hosts=[config.GHOST_SPEAKER_IP], discovery_timeout=5)
            browser.stop_discovery()
            if not casts:
                raise RuntimeError(f"speaker {config.GHOST_SPEAKER_NAME!r} not found")
            casts[0].wait(timeout=10)
            self._cast = casts[0]
        return self._cast

    def _play(self, clip):
        url = f"http://{_my_ip()}:{config.PORT}/ghost/{clip}"
        for attempt in (1, 2):  # one reconnect if the cached connection went stale
            try:
                cc = self._speaker()
                cc.set_volume(config.GHOST_VOLUME)
                cc.media_controller.play_media(url, "audio/mpeg")
                cc.media_controller.block_until_active(timeout=10)
                return
            except Exception as e:
                log.warning("ghost cast attempt %d failed: %s", attempt, e)
                self._cast = None
                if attempt == 2:
                    raise

    def haunt(self, clip=None, force=False):
        """Play a line now (off-thread). Motion calls this; force skips hours + cooldown.
        Returns the clip chosen, or None when skipped."""
        with self._lock:
            if not force and (not self.armed() or self.cooling()):
                return None
            clips = self.clips()
            if not clips:
                return None
            if clip is None:
                clip = self._next_clip()
            elif clip not in clips:
                raise ValueError(f"no clip {clip!r}")
            self.last_played = time.time()
            self.last_clip = clip
            self.played_tonight += 1

        def run():
            try:
                self._play(clip)
                self.last_error = None
                log.info("ghost played %s", clip)
            except Exception as e:
                self.last_error = f"{datetime.now():%H:%M:%S} {e}"
                log.error("ghost failed: %s", e)

        threading.Thread(target=run, daemon=True).start()
        return clip

    def status(self):
        return {"enabled": self.enabled, "armed": self.armed(), "in_hours": self.in_hours(),
                "hours": list(config.GHOST_HOURS), "all_day": self.all_day, "cooling": self.cooling(),
                "cooldown_s": config.GHOST_COOLDOWN_SECONDS, "clips": len(self.clips()),
                "played": self.played_tonight, "last_clip": self.last_clip,
                "last_error": self.last_error, "speaker": config.GHOST_SPEAKER_NAME}
