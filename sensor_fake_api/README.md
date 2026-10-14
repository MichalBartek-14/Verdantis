# Fake sensor API

A standalone FastAPI service that mimics the real, currently-offline
`geosenzor-api` (see `../data/verdantis-sensor-infra-reference.md`) closely
enough that `docs/sensors/simulation.html` can be built and demoed against it
today, then pointed at the real API later by changing one constant.

Not wired into the rest of this repo in any way - `config.py`/`clients.py`
never import this folder, and nothing here writes into `outputs/` or `docs/`.
It's a dev/demo tool you run yourself, same "nothing runs automatically"
posture as everything else in this repo (see the root `CLAUDE.md`).

## What it simulates

- **6 static sensors** (`sensor01`-`sensor06`), spread in a grid across the
  Devinska plot's real `alert_bbox`. Each reports temperature + soil moisture
  on the same cadence/shape as the real `tempsensor` MQTT topic
  (`sensor_id`, `location`, `temperature`, `soil_moisture`, `date_time`).
- **1 moving sensor** (`tractor01`), linearly interpolating back and forth
  between two waypoints inside the same bbox - a tractor/vehicle working the
  plot. Reports position on the same shape as the real `geosensor` topic
  (`latitude`, `longitude`, `altitude`, `satellites`, `hdop`, `fix`).
- A **crop/season critical soil-moisture table** (`config.json`'s
  `crop_seasonal_critical_soil_moisture`) - deterministic, swappable per crop
  and season without touching any code, feeding the dashboard's
  "critically low" status bar.

Every reading's *value* is a deterministic function of (sensor, timestamp) -
see `simulator.py` - so restarting the server doesn't change the shape of the
data, only how much of it has accumulated. 10 days of history is backfilled
at startup (`backfill_interval_seconds`, default 15 min/point); after that, one
new reading per sensor is appended every `update_interval_seconds` (default
30s, matching the real sensor's observed cadence).

## Run it

```bash
pip install -r sensor_fake_api/requirements.txt
cd sensor_fake_api
uvicorn app:app --reload --port 8000
```

Then open `docs/sensors/simulation.html` (e.g. via
`python -m http.server` from `docs/`) - it polls `http://localhost:8000` by
default (see the `API_BASE` constant near the top of that page's script).

## Endpoints

Mirrors the real API's contract (query params, `{"data": [...]}` envelope,
chronological order, optional `X-API-Key` header - see
`../data/verdantis-sensor-infra-reference.md` section 6):

- `GET /api/v1/temperature` - `sensor_id`, `location`, `from`, `to`, `last`
  (default 200, clamped to 1000), `after_id`
- `GET /api/v1/location-data` - same params, for the moving sensor's position
- `GET /health` - liveness + current row counts

One addition with **no** real-API equivalent, clearly namespaced so it's
never mistaken for part of the contract above:

- `GET /api/v1/sim/config` - bbox, the static sensor registry (id/location/
  lat/lon - the real API never returns coordinates for a tempsensor, only a
  location *label*; a real deployment gets that mapping from
  `clients/<slug>.json`'s `sensor_location` instead, same idea here via
  `config.json`), and the active crop/season's critical soil-moisture value.

`require_api_key` in `config.json` defaults to `false` for frictionless local
demoing; flip it and set `api_key` to exercise the same `401` behavior the
real API has.

## Swapping to the real API later

`docs/sensors/simulation.html` only ever calls the two real-shaped endpoints
plus `/api/v1/sim/config` for sensor placement/thresholds. Pointing it at the
real service once it's live again means: change `API_BASE` to
`https://api.verdantisdata.eu`, supply a real `X-API-Key`, and replace the
`/api/v1/sim/config` call with whatever static sensor-placement/threshold
source the real deployment ends up using (e.g. a `clients/<slug>.json`-style
file) - nothing about the polling/charting/mapping logic needs to change.
