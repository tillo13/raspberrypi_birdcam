"""Group motion captures into bird visits.

Every capture already carries its own timestamp in its filename, so a visit is just
a run of motion files with no long gap between them — no new datastore needed for
the grouping itself. Conditions at trigger time go to a JSONL side-log and are
joined back on here, which is what makes "they came while the pressure was falling"
a question the dashboard can answer.
"""
import json
from collections import deque
from datetime import datetime

import config

TS_FORMAT = "%Y%m%d_%H%M%S"
TS_LEN = 15                 # len("YYYYmmdd_HHMMSS")
EVENT_TAIL = 5000           # most recent side-log lines to consider


def parse_ts(name):
    """Datetime from a capture filename, or None if it isn't one of ours."""
    try:
        return datetime.strptime(name[:TS_LEN], TS_FORMAT)
    except ValueError:
        return None


def log_event(name, weather):
    """Append one motion trigger and the conditions it happened in."""
    config.LOG_DIR.mkdir(exist_ok=True)
    row = {"file": name}
    if weather:
        row.update(temp_c=weather["temp_c"], humidity=weather["humidity"],
                   pressure=weather["pressure"])
    with open(config.EVENTS_LOG, "a") as fh:
        fh.write(json.dumps(row) + "\n")


def _load_events():
    if not config.EVENTS_LOG.exists():
        return {}
    events = {}
    with open(config.EVENTS_LOG) as fh:
        for line in deque(fh, maxlen=EVENT_TAIL):
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if "file" in row:
                events[row["file"]] = row
    return events


def _motion_files(files):
    """(datetime, name) for every motion capture, oldest first."""
    out = []
    for name in files:
        if "_motion" not in name:
            continue
        ts = parse_ts(name)
        if ts:
            out.append((ts, name))
    out.sort()
    return out


def build(files, gap=None, limit=None):
    """Cluster motion captures into visits, newest visit first."""
    gap = config.VISIT_GAP_SECONDS if gap is None else gap
    limit = config.VISIT_LIMIT if limit is None else limit
    events = _load_events()

    visits = []
    for ts, name in _motion_files(files):
        if visits and (ts - visits[-1]["_end"]).total_seconds() <= gap:
            visit = visits[-1]
        else:
            visit = {"_start": ts, "_end": ts, "stills": [], "clips": [],
                     "temp_c": None, "humidity": None, "pressure": None}
            visits.append(visit)
        visit["_end"] = ts
        (visit["clips"] if name.endswith((".mp4", ".h264")) else
         visit["stills"]).append(name)
        row = events.get(name)
        if row and visit["temp_c"] is None:
            visit["temp_c"] = row.get("temp_c")
            visit["humidity"] = row.get("humidity")
            visit["pressure"] = row.get("pressure")

    out = []
    for v in visits:
        out.append({
            "start": v["_start"].isoformat(timespec="seconds"),
            "end": v["_end"].isoformat(timespec="seconds"),
            "duration_s": int((v["_end"] - v["_start"]).total_seconds()),
            "triggers": len(v["stills"]),
            "thumbnail": v["stills"][0] if v["stills"] else None,
            "clip": v["clips"][0] if v["clips"] else None,
            "temp_c": v["temp_c"],
            "humidity": v["humidity"],
            "pressure": v["pressure"],
        })
    out.reverse()
    return out[:limit]


def histogram(files, day=None):
    """Motion triggers per hour for one day. Returns 24 counts, midnight first."""
    day = day or datetime.now().date()
    hours = [0] * 24
    for ts, name in _motion_files(files):
        if ts.date() == day and not name.endswith((".mp4", ".h264")):
            hours[ts.hour] += 1
    return hours


def days_with_motion(files):
    """Every date that has at least one motion capture, newest first."""
    days = {ts.date().isoformat() for ts, _ in _motion_files(files)}
    return sorted(days, reverse=True)
