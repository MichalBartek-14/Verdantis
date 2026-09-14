"""
Sensor ingestion - stationary temperature/soil-moisture sensor
================================================================
Pulls fresh readings from Devinska's live field-sensor API (see
data/verdantis-sensor-infra-reference.md - a separately-run FastAPI service,
not built by this repo), merges them with whatever's already been dropped
into sensor_uploads/<slug>/temperature/, and writes
outputs/<slug>/sensor_temperature.json in the shape
docs/_template/index.html's plot-location map expects (see
publish_site.py's own comment for the exact shape it copies). Written
against the first real sample seen from that API - deliberately ONE small
deterministic parser for THIS format, per CLAUDE.md's "Live sensor data"
note, not a standing "figure out the format every run" step. If a
differently-shaped export shows up later (a different vendor/client, or a
v2 of this same API), add another parse function and dispatch on it rather
than trying to make this one parser guess formats.

Two ways a reading ends up in sensor_uploads/<slug>/temperature/:
  1. Live: this script itself, via fetch_live_readings() below - one GET
     against config.SENSOR_API_BASE_URL + "/api/v1/temperature" per run
     (skipped if no API key is configured - see resolve_api_key()), saved
     as a timestamped .json file so every pull stays in that folder's
     git-tracked audit trail, same as a hand-dropped file would.
  2. Manual: a human drops in whatever the sensor/vendor exports, any
     filename. The one shape actually seen so far is repeated blocks of
     "key : value" lines separated by a blank line, e.g.:

         id            : 1455
         sensor_id     : sensor01
         location      : dnv
         temperature   : 24.56
         soil_moisture : 2416
         date_time     : 2026-09-14T19:26:28+00:00

Both shapes carry the same fields, just as JSON vs. plain text - see
load_raw_readings() for the dispatch. "soil_moisture" is passed through as
the sensor's raw reported number - its unit/calibration isn't documented
by the API, so it's published as-is rather than guessed at (e.g.
relabelled "_pct"). temperature/date_time are the only fields the
published site's map actually uses today (see docs/_template/index.html);
id/sensor_id/location are read here only to dedupe, to drive incremental
after_id polling, and to sanity-check the assumption (see below) that this
is one single stationary sensor.

EVERY file currently sitting in sensor_uploads/<slug>/temperature/ is
parsed and merged, not just the newest - each drop (live or manual)
generally overlaps the previous one, so readings across all files are
deduplicated by their "id" field before being sorted oldest-first. This
script assumes ONE stationary sensor per client (matching CLAUDE.md's
model: fixed location set once in clients/<slug>.json's "sensor_location")
- if more than one distinct sensor_id ever shows up in the same client's
drops, that assumption no longer holds and this script says so loudly
rather than silently averaging two different physical sensors together.

sensor_track.json (the OTHER live-sensor file - the position tracker) is
NOT handled here: that's a different physical device with no known export
format yet - see sensor_uploads/<slug>/track/'s README.

Run:    python ingest_sensor_data.py --client <slug>
        python ingest_sensor_data.py --client <slug> --no-fetch   # local drops only, no network
        python ingest_sensor_data.py --all
"""
import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import requests

import clients
import config

SKIP_NAMES = {".gitkeep"}
DEFAULT_BACKFILL = 100  # rows to pull via `last=` on a client's very first live fetch (no local drop history yet) - within the API's documented 1-1000 clamp
REQUEST_TIMEOUT = 15    # seconds - matches utils/weather.py's request style; this is a small single-vCPU VPS, not a heavy batch job


def parse_blocks(text: str) -> list[dict]:
    """Blank-line-separated "key : value" blocks -> list of raw {key: value}
    string dicts. No type coercion here - that's parse_reading()'s job -
    so one malformed block doesn't take the whole file's parse down."""
    blocks = []
    current: dict = {}
    for line in text.splitlines():
        if not line.strip():
            if current:
                blocks.append(current)
                current = {}
            continue
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        current[key.strip()] = value.strip()
    if current:
        blocks.append(current)
    return blocks


def load_raw_readings(path: Path) -> list[dict]:
    """One dropped file -> list of raw reading dicts, whichever of the two
    shapes this drop zone sees: a .json file (this script's own saved copy
    of the live API's {"data": [...]} response envelope - see
    fetch_live_readings() below) or anything else (the blank-line
    "key : value" block format above, for a hand-dropped/manually-exported
    sample). parse_reading() takes either shape unchanged - the API's JSON
    values are already the right types/strings, just like a parsed text
    block's string values coerce the same way."""
    if path.suffix.lower() == ".json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        rows = payload.get("data", []) if isinstance(payload, dict) else payload
        return rows if isinstance(rows, list) else []
    return parse_blocks(path.read_text(encoding="utf-8"))


def parse_reading(block: dict) -> dict | None:
    """One raw block -> one typed reading (still keyed by internal "id" and
    "sensor_id" for load_all_readings()'s callers to dedupe/sanity-check
    with - both stripped back out before writing the published JSON). None
    if the block is missing/garbling something essential, e.g. a truncated
    read mid-poll - skip that one reading, don't fail the whole file."""
    try:
        reading = {
            "id": int(block["id"]),
            "sensor_id": block.get("sensor_id", ""),
            "time": datetime.fromisoformat(block["date_time"]).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "temperature_c": float(block["temperature"]),
        }
    except (KeyError, ValueError):
        return None
    if "soil_moisture" in block:
        try:
            reading["soil_moisture"] = float(block["soil_moisture"])
        except ValueError:
            pass
    return reading


def load_all_readings(slug: str, verbose: bool = True) -> list[dict]:
    """Every file currently in sensor_uploads/<slug>/temperature/, parsed
    (not deduped/sorted yet - see ingest_temperature(), the public entry
    point for that). Also reused standalone, quietly, by latest_known_id()
    below to find the highest already-known reading id for incremental
    after_id polling."""
    src_dir = Path("sensor_uploads") / slug / "temperature"
    files = sorted(p for p in src_dir.glob("*") if p.is_file() and p.name not in SKIP_NAMES)
    all_readings = []
    for path in files:
        raw_blocks = load_raw_readings(path)
        n_ok = 0
        for block in raw_blocks:
            reading = parse_reading(block)
            if reading is None:
                if verbose:
                    print(f"  {path.name}: skipping one unparseable reading: {block!r}")
                continue
            all_readings.append(reading)
            n_ok += 1
        if verbose:
            print(f"  {path.name}: {n_ok}/{len(raw_blocks)} reading(s) parsed")
    return all_readings


def latest_known_id(slug: str) -> int | None:
    """Highest reading `id` already sitting in this client's local drops -
    lets fetch_live_readings() ask the API for only what's new (`after_id`)
    instead of re-pulling history the drop zone already has. None if
    there's no local history yet (first-ever run for this client)."""
    ids = [r["id"] for r in load_all_readings(slug, verbose=False)]
    return max(ids) if ids else None


def resolve_api_key(slug: str) -> str | None:
    """API key for the live sensor API - never read from any git-tracked
    file (see secrets/README.md). Checks, in order: a per-client env var
    (VERDANTIS_SENSOR_API_KEY_<SLUG>), the generic env var
    (VERDANTIS_SENSOR_API_KEY), then a local secrets/<slug>_sensor_api_key.txt
    file (gitignored). None if none of those are set, in which case
    fetch_live_readings() is skipped and this script falls back to parsing
    whatever's already in sensor_uploads/<slug>/temperature/."""
    env_key = os.environ.get(f"VERDANTIS_SENSOR_API_KEY_{slug.upper()}") or os.environ.get("VERDANTIS_SENSOR_API_KEY")
    if env_key:
        return env_key.strip()
    key_file = Path("secrets") / f"{slug}_sensor_api_key.txt"
    if key_file.exists():
        key = key_file.read_text(encoding="utf-8").strip()
        return key or None
    return None


def fetch_live_readings(slug: str, api_key: str, after_id: int | None) -> Path | None:
    """One GET against the live temperature API (see
    data/verdantis-sensor-infra-reference.md section 6) - `after_id` when
    local history already exists (the API's own "everything new since I
    last checked" primitive), otherwise `last=DEFAULT_BACKFILL` to seed an
    initial batch. Saves the raw JSON response into
    sensor_uploads/<slug>/temperature/ - the SAME git-tracked drop zone a
    manual export lands in, so a live pull is ingested identically to a
    hand-dropped file and stays in the audit trail. Network/API failures
    are reported and swallowed, never raised - a flaky poll should degrade
    to "parse whatever's already dropped locally", not take the whole run
    down (same soft-fail contract as a missing API key, per
    secrets/README.md)."""
    params = {"after_id": after_id} if after_id is not None else {"last": DEFAULT_BACKFILL}
    try:
        resp = requests.get(
            f"{config.SENSOR_API_BASE_URL}/api/v1/temperature",
            headers={"X-API-Key": api_key}, params=params, timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        payload = resp.json()
    except (requests.RequestException, ValueError) as exc:
        print(f"  live API fetch failed ({exc}) - falling back to whatever's already dropped locally.")
        return None

    rows = payload.get("data", []) if isinstance(payload, dict) else []
    if not rows:
        print("  live API: no new readings.")
        return None

    out_dir = Path("sensor_uploads") / slug / "temperature"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = out_dir / f"{stamp}_api-pull.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    print(f"  live API: {len(rows)} new reading(s) saved to {out_path}")
    return out_path


def ingest_temperature(slug: str) -> list[dict]:
    all_readings = load_all_readings(slug)
    if not all_readings:
        print(f"  no files in sensor_uploads/{slug}/temperature/ yet - nothing to ingest.")
        return []

    by_id: dict = {}
    for reading in all_readings:
        by_id[reading["id"]] = reading  # later files (sorted filename order) win on a duplicate id; content should be identical anyway
    readings = sorted(by_id.values(), key=lambda r: (r["time"], r["id"]))

    sensor_ids = {r["sensor_id"] for r in readings if r["sensor_id"]}
    if len(sensor_ids) > 1:
        print(f"  WARNING: {len(sensor_ids)} distinct sensor_id values found ({sorted(sensor_ids)}) - this script "
              f"assumes ONE stationary sensor per client (see module docstring). Readings from all of them are "
              f"being merged into a single feed/location, which is probably wrong once a second physical sensor "
              f"is really in play - split this client's temperature/ drops or extend this script instead of "
              f"trusting the output as-is.")

    for r in readings:
        del r["id"], r["sensor_id"]  # internal dedup/sanity-check keys only - not part of the published shape
    return readings


def run(client: dict, fetch: bool = True):
    slug = client["slug"]
    print(f"=== {slug} ===")

    if fetch and client.get("live_sensor_feed"):
        api_key = resolve_api_key(slug)
        if api_key:
            fetch_live_readings(slug, api_key, latest_known_id(slug))
        else:
            print("  no live API key configured (see secrets/README.md) - parsing local drops only.")

    readings = ingest_temperature(slug)
    if not readings:
        return

    out_dir = Path("outputs") / slug
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "sensor_temperature.json"
    with open(out_path, "w") as f:
        json.dump(readings, f, indent=2)
    print(f"  saved: {out_path} ({len(readings)} reading(s), {readings[0]['time']} to {readings[-1]['time']})")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--client", help="Ingest a single client slug.")
    group.add_argument("--all", action="store_true", help="Ingest every client in clients/.")
    parser.add_argument("--no-fetch", action="store_true",
                         help="Skip the live API pull - parse only what's already in sensor_uploads/<slug>/temperature/.")
    args = parser.parse_args()

    slugs = clients.list_clients() if args.all else [args.client]
    for slug in slugs:
        client = clients.load_client(slug)  # validates the slug against clients/<slug>.json before touching any files
        run(client, fetch=not args.no_fetch)
