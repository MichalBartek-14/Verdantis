# Sensor uploads - Devinska

Drop zone for the raw exports from Devinska's two field sensors. Unlike `data/` (gitignored,
large geospatial pipeline inputs), this folder **is committed to git** - files here are
meant to be small and reviewable.

- `track/` - the position tracker's raw export (~1 reading/minute, position only).
- `temperature/` - the stationary sensor's raw export (temperature + soil moisture; it
  doesn't move - its fixed location is set once in `clients/devinska.json`'s
  `sensor_location`, not read from these files).

## What to drop in, and how often

`temperature/` gets files two ways now:

1. **Automatically** - `ingest_sensor_data.py --client devinska` fetches new readings
   itself from the live API (`config.SENSOR_API_BASE_URL` + `/api/v1/temperature`, see
   `data/verdantis-sensor-infra-reference.md` §6 and `secrets/README.md` for the API
   key) on every run, and saves the raw response as a timestamped `<UTC>_api-pull.json`
   file right here - same drop zone, so a live pull and a manual export are ingested
   identically. This is the normal path going forward; nothing to do by hand.
2. **Manually** - drop in whatever the sensor/vendor exports by hand, any filename
   (e.g. `2026-09-14_api-pull.txt`), just don't overwrite a previous drop, so there's a
   record of what arrived when. The one shape seen so far is repeated blank-line-
   separated blocks of "key : value" lines:

   ```
   id            : 1455
   sensor_id     : sensor01
   location      : dnv
   temperature   : 24.56
   soil_moisture : 2416
   date_time     : 2026-09-14T19:26:28+00:00
   ```

Either way, `ingest_sensor_data.py` merges and deduplicates every file in this folder by
`id` each run, so drops (live or manual) are expected to overlap - that's fine, don't
trim a file down before dropping it in. `soil_moisture` is passed through as the
sensor's raw reported number; its unit/calibration isn't documented by the API, so it
isn't relabelled or rescaled.

`track/`: no real export has been seen yet - format still unknown, `ingest_sensor_data.py`
does not read this folder at all yet.

## What happens after `ingest_sensor_data.py` runs

`python ingest_sensor_data.py --client devinska` fetches new readings (see above,
skippable with `--no-fetch`), then reads every file in `temperature/` (not just the
newest), parses it, and writes `outputs/devinska/sensor_temperature.json` in the shape
`docs/_template/index.html`'s map expects. Then the normal
`python publish_site.py --client devinska` step publishes it like everything else in
this pipeline. `track/` isn't ingested yet - see above.
