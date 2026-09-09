"""Ambient conditions from the Sense HAT, corrected for the Pi's own heat.

The HAT stacks straight onto the Pi, so its sensors sit in the CPU's exhaust and
read hot: 37.2 C on the board while the CPU was at 53.7 C. Subtracting a share of
that gap pulls the reading back toward ambient, but how big a share depends on the
enclosure, so CPU_HEAT_FACTOR is a config knob and every response carries the raw
numbers alongside the corrected one. Treat the corrected value as an estimate until
it has been checked against a real thermometer.
"""
import math
import threading
import time

import config

_lock = threading.Lock()
_cache = {"at": 0.0, "data": None}


def _cpu_temp_c():
    with open("/sys/class/thermal/thermal_zone0/temp") as fh:
        return int(fh.read().strip()) / 1000.0


def _saturation_vp(t_c):
    """Saturation vapour pressure in hPa (Magnus)."""
    return 6.112 * math.exp((17.67 * t_c) / (t_c + 243.5))


def _read_sensors():
    from utilities import sensehat_utils
    sense = sensehat_utils.sense
    raw_t = (sense.get_temperature_from_humidity()
             + sense.get_temperature_from_pressure()) / 2
    raw_rh = sense.get_humidity()
    pressure = sense.get_pressure()
    if not pressure:            # the first read after init comes back 0
        pressure = sense.get_pressure()
    return raw_t, raw_rh, pressure


def read(force=False):
    """Current conditions, cached. Returns None if the sensors can't be read."""
    now = time.time()
    with _lock:
        cached = _cache["data"]
        if cached and not force and now - _cache["at"] < config.WEATHER_CACHE_SECONDS:
            return cached
    try:
        raw_t, raw_rh, pressure = _read_sensors()
        cpu_t = _cpu_temp_c()
    except Exception:
        return None

    temp_c = raw_t - (cpu_t - raw_t) / config.CPU_HEAT_FACTOR
    # A heat-soaked sensor under-reads relative humidity, because the warmer air it
    # sees could hold more moisture than the air outside actually does.
    humidity = min(100.0, raw_rh * _saturation_vp(raw_t) / _saturation_vp(temp_c))

    data = {
        "temp_c": round(temp_c, 1),
        "temp_f": round(temp_c * 9 / 5 + 32, 1),
        "humidity": round(humidity, 1),
        "pressure": round(pressure, 1),
        "raw_temp_c": round(raw_t, 1),
        "raw_humidity": round(raw_rh, 1),
        "cpu_temp_c": round(cpu_t, 1),
        "corrected": True,
        "at": now,
    }
    with _lock:
        _cache["at"] = now
        _cache["data"] = data
    return data
