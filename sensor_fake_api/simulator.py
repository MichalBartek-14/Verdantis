"""
Synthetic sensor generation - 6 static tempsensors + 1 moving geosensor
=========================================================================
Pure, deterministic generator functions: every reading's VALUE is a
function of (sensor config, timestamp) alone, via a seeded RNG keyed off
the sensor id + minute - not a running random walk that needs state
carried between calls. That means app.py doesn't need to persist
anything to reproduce a given moment's reading, and a restarted server
picks the same shape of data back up rather than starting from a
different random baseline. What genuinely accumulates over time is just
*which* timestamps have been emitted yet (app.py's in-memory id-stamped
history + the background tick that appends to it) - see app.py.

Field shapes mirror the real API's TempMeasurement/GeoMeasurement
payloads (see data/verdantis-sensor-infra-reference.md section 4) so
this is a drop-in stand-in: a frontend built against this fake API's
/api/v1/temperature and /api/v1/location-data needs only a base-URL
change to point at the real one once it's live again.
"""
import hashlib
import math
import random
from datetime import datetime, timezone

# Fixed reference instant the moving sensor's triangle-wave path is phased
# against, so its position is a pure function of absolute time (not "time
# since server start") - restarting the server doesn't jump the tractor.
POSITION_EPOCH = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _seed(sensor_id: str, salt: str) -> int:
    return int(hashlib.sha256(f"{sensor_id}:{salt}".encode()).hexdigest()[:8], 16)


def temp_reading_value(sensor_cfg: dict, t: datetime) -> float:
    """Diurnal cycle (peaks mid-afternoon) + a slow per-sensor wave + small
    per-minute jitter - same "mostly flat, drifts a bit, occasionally
    ticks up/down a notch" texture as the real Devinska sample (see
    docs/sensors/data/sensor_temperature.json)."""
    base = sensor_cfg["baseline_temp_c"]
    hour = t.hour + t.minute / 60
    diurnal = 2.2 * math.sin(2 * math.pi * (hour - 9) / 24)
    phase = (_seed(sensor_cfg["sensor_id"], "temp-phase") % 1000) / 1000 * 2 * math.pi
    slow_wave = 0.4 * math.sin(2 * math.pi * (t.timestamp() / (3600 * 6)) + phase)
    rng = random.Random(_seed(sensor_cfg["sensor_id"], f"temp:{int(t.timestamp() // 60)}"))
    jitter = rng.uniform(-0.06, 0.06)
    return round(base + diurnal + slow_wave + jitter, 2)


def soil_moisture_value(sensor_cfg: dict, t: datetime) -> float:
    """Noisy baseline with a slow per-sensor drift and an occasional
    larger spike - matches the real sample's raw-unit jumpiness (e.g.
    2559 -> 2683 -> 2595 within a minute) rather than smooth noise."""
    base = sensor_cfg["baseline_soil_moisture"]
    scale = sensor_cfg["soil_moisture_noise"]
    phase = (_seed(sensor_cfg["sensor_id"], "moist-phase") % 1000) / 1000 * 2 * math.pi
    slow_drift = scale * 0.6 * math.sin(2 * math.pi * (t.timestamp() / (3600 * 30)) + phase)
    rng = random.Random(_seed(sensor_cfg["sensor_id"], f"moist:{int(t.timestamp() // 60)}"))
    jitter = rng.uniform(-scale, scale)
    spike = scale * 3 * rng.choice([-1, 1]) if rng.random() < 0.04 else 0
    return round(max(0.0, base + slow_drift + jitter + spike), 1)


def moving_position(moving_cfg: dict, t: datetime) -> tuple[float, float]:
    """Linear back-and-forth (triangle wave) between waypoint_a and
    waypoint_b, one full A->B->A cycle every traverse_minutes - a
    tractor/vehicle working the plot, not a random walk, so it's always
    inside the bbox and its position at any instant is reproducible."""
    period = moving_cfg["traverse_minutes"] * 60 * 2
    elapsed = (t - POSITION_EPOCH).total_seconds() % period
    half = period / 2
    frac = elapsed / half if elapsed <= half else (period - elapsed) / half
    a, b = moving_cfg["waypoint_a"], moving_cfg["waypoint_b"]
    lat = a["lat"] + (b["lat"] - a["lat"]) * frac
    lon = a["lon"] + (b["lon"] - a["lon"]) * frac
    return round(lat, 6), round(lon, 6)


def make_temp_reading(sensor_cfg: dict, t: datetime, reading_id: int) -> dict:
    return {
        "id": reading_id,
        "sensor_id": sensor_cfg["sensor_id"],
        "location": sensor_cfg["location"],
        "temperature": temp_reading_value(sensor_cfg, t),
        "soil_moisture": soil_moisture_value(sensor_cfg, t),
        "date_time": t.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def make_geo_reading(moving_cfg: dict, t: datetime, reading_id: int) -> dict:
    lat, lon = moving_position(moving_cfg, t)
    rng = random.Random(_seed(moving_cfg["sensor_id"], f"geo:{int(t.timestamp() // 60)}"))
    return {
        "id": reading_id,
        "sensor_id": moving_cfg["sensor_id"],
        "location": moving_cfg["location"],
        "latitude": lat,
        "longitude": lon,
        "altitude": round(moving_cfg["altitude_m"] + rng.uniform(-0.6, 0.6), 1),
        "satellites": rng.randint(8, 12),
        "hdop": round(rng.uniform(0.8, 1.5), 2),
        "fix": "3D",
        "date_time": t.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
