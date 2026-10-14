"""
Fake sensor API - FastAPI stand-in for the real `geosenzor-api` service
=========================================================================
Serves /api/v1/temperature and /api/v1/location-data with the same
request/response shape as the real, currently-offline sensor API (see
data/verdantis-sensor-infra-reference.md section 6) - same query params
(sensor_id, location, from, to, last, after_id), same {"data": [...]}
envelope, same chronological ordering, same optional X-API-Key header.
7 synthetic sensors: 6 static tempsensors + 1 moving geosensor simulating
a tractor crossing the plot (see simulator.py for the generation math,
config.json for the bbox/sensor registry/crop-season thresholds).

This is a standalone dev/demo tool, not part of the main batch pipeline
(config.py/clients.py never import this folder, and nothing here writes
to outputs/ or docs/) - it exists so docs/sensors/simulation.html has
something live to poll locally while the real field-sensor API is down.
Swapping the dashboard over to the real API later is meant to be a
base-URL change, nothing structural - see README.md.

Run:  pip install -r sensor_fake_api/requirements.txt
      uvicorn app:app --reload --port 8000        (from inside sensor_fake_api/)
"""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

import simulator

CONFIG_PATH = Path(__file__).parent / "config.json"
DEFAULT_LAST = 200
MAX_LAST = 1000

with open(CONFIG_PATH, encoding="utf-8") as f:
    CONFIG = json.load(f)

STATE = {"temperature": [], "location": [], "next_temp_id": 1, "next_geo_id": 1}


def build_backfill(now: datetime) -> None:
    """Seed STATE with backfill_days of history at backfill_interval_seconds
    resolution, oldest first, ids assigned in chronological order - run
    once at startup so the dashboard's "past 10 days" chart has something
    to show immediately rather than waiting ~10 days for live ticks to
    accumulate it."""
    start = now - timedelta(days=CONFIG["backfill_days"])
    interval = CONFIG["backfill_interval_seconds"]
    t = start
    while t <= now:
        for cfg in CONFIG["static_sensors"]:
            STATE["temperature"].append(simulator.make_temp_reading(cfg, t, STATE["next_temp_id"]))
            STATE["next_temp_id"] += 1
        STATE["location"].append(simulator.make_geo_reading(CONFIG["moving_sensor"], t, STATE["next_geo_id"]))
        STATE["next_geo_id"] += 1
        t += timedelta(seconds=interval)


def live_tick(now: datetime) -> None:
    """One new reading per sensor, appended with the next sequential id -
    called by the startup backfill's final tick AND by the background
    poll loop below, so "backfill" and "live" are the same code path at
    different timestamps, not two separate implementations to keep in sync."""
    for cfg in CONFIG["static_sensors"]:
        STATE["temperature"].append(simulator.make_temp_reading(cfg, now, STATE["next_temp_id"]))
        STATE["next_temp_id"] += 1
    STATE["location"].append(simulator.make_geo_reading(CONFIG["moving_sensor"], now, STATE["next_geo_id"]))
    STATE["next_geo_id"] += 1


app = FastAPI(title="Verdantis fake sensor API", docs_url="/docs")

# Wide open, read-only, no secrets of consequence (the demo API key below
# is literally named "change-me") - this is a localhost dev tool a static
# site's browser JS polls directly, same CORS posture as Open-Meteo/the
# other public APIs assets/weather.js already calls from the browser.
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["GET"], allow_headers=["*"],
)


@app.on_event("startup")
async def on_startup():
    build_backfill(datetime.now(timezone.utc))
    import asyncio
    asyncio.create_task(poll_loop())


async def poll_loop():
    import asyncio
    while True:
        await asyncio.sleep(CONFIG["update_interval_seconds"])
        live_tick(datetime.now(timezone.utc))


def check_api_key(x_api_key: Optional[str]) -> None:
    if not CONFIG["require_api_key"]:
        return
    if x_api_key != CONFIG["api_key"]:
        raise HTTPException(status_code=401, detail="missing/invalid X-API-Key")


def filter_rows(
    rows: list[dict], sensor_id: Optional[str], location: Optional[str],
    from_: Optional[str], to: Optional[str], last: Optional[int], after_id: Optional[int],
) -> list[dict]:
    out = rows
    if sensor_id:
        out = [r for r in out if r["sensor_id"] == sensor_id]
    if location:
        out = [r for r in out if r["location"] == location]
    if from_:
        out = [r for r in out if r["date_time"] >= from_]
    if to:
        out = [r for r in out if r["date_time"] <= to]
    if after_id is not None:
        out = [r for r in out if r["id"] > after_id]
        return out  # after_id means "everything new" - no further clamping
    n = min(last, MAX_LAST) if last else DEFAULT_LAST
    return out[-n:]


@app.get("/api/v1/temperature")
async def get_temperature(
    sensor_id: Optional[str] = None, location: Optional[str] = None,
    from_: Optional[str] = Query(None, alias="from"), to: Optional[str] = None,
    last: Optional[int] = None, after_id: Optional[int] = None,
    x_api_key: Optional[str] = Header(None),
):
    check_api_key(x_api_key)
    rows = filter_rows(STATE["temperature"], sensor_id, location, from_, to, last, after_id)
    return {"data": rows}


@app.get("/api/v1/location-data")
async def get_location_data(
    sensor_id: Optional[str] = None, location: Optional[str] = None,
    from_: Optional[str] = Query(None, alias="from"), to: Optional[str] = None,
    last: Optional[int] = None, after_id: Optional[int] = None,
    x_api_key: Optional[str] = Header(None),
):
    check_api_key(x_api_key)
    rows = filter_rows(STATE["location"], sensor_id, location, from_, to, last, after_id)
    return {"data": rows}


@app.get("/api/v1/sim/config")
async def get_sim_config():
    """NOT part of the real API's contract (hence the /sim/ prefix) - a
    convenience endpoint so the dashboard doesn't have to hardcode the
    bbox/sensor registry/threshold separately from this file, the same
    way a real deployment would get sensor placement from
    clients/<slug>.json's sensor_location rather than from the API
    itself (temperature readings carry a bare location *label*, not
    coordinates - see data/verdantis-sensor-infra-reference.md section 4)."""
    thresholds = {k: v for k, v in CONFIG["crop_seasonal_critical_soil_moisture"].items() if k != "_comment"}
    crop, season = CONFIG["active_crop"], CONFIG["active_season"]
    return {
        "bbox": CONFIG["bbox"],
        "update_interval_seconds": CONFIG["update_interval_seconds"],
        "static_sensors": [
            {"sensor_id": s["sensor_id"], "location": s["location"], "lat": s["lat"], "lon": s["lon"]}
            for s in CONFIG["static_sensors"]
        ],
        "moving_sensor": {
            "sensor_id": CONFIG["moving_sensor"]["sensor_id"],
            "location": CONFIG["moving_sensor"]["location"],
        },
        "active_crop": crop,
        "active_season": season,
        "critical_soil_moisture": thresholds[crop][season],
        "crop_seasonal_critical_soil_moisture": thresholds,
    }


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "now": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "temperature_readings": len(STATE["temperature"]),
        "location_readings": len(STATE["location"]),
    }
