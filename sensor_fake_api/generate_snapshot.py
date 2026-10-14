"""
Generate a static snapshot of the synthetic sensor network
=============================================================
The published site (docs/) has no backend - nothing on it can poll
sensor_fake_api/app.py, which only runs on whoever's own machine starts
it (see README.md). So docs/sensors/simulation.html reads a static
snapshot instead of polling live: this script runs app.py's exact same
generation path (simulator.generate_backfill/sim_config_payload) once
and writes the result straight into docs/sensors/data/ as three JSON
files, the same "static site, no backend" pattern every other page here
already uses (compare publish_site.py writing outputs/<slug>/*.json into
docs/c/<slug>/data/).

Trade-off, spelled out: this is a snapshot, not a live feed - the
dashboard stops "moving" the moment you stop re-running this script. If
genuinely live-ticking data for every visitor is wanted later, that
needs sensor_fake_api/app.py deployed somewhere publicly reachable
instead (see README.md's "Swapping to the real API later" section - the
same base-URL-change design works for a real public backend too, this
script is just the zero-infrastructure option for now).

Run:  python sensor_fake_api/generate_snapshot.py
      (from the repo root, or from inside sensor_fake_api/ - resolves
      paths either way)

Re-run it whenever you want the dashboard's "past 10 days" window to
actually cover the last 10 days, or want a different sensor layout/
threshold (edit config.json first) baked in. Nothing here runs
automatically - same "no CI/cron" posture as the rest of this repo.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

import simulator

HERE = Path(__file__).parent
CONFIG_PATH = HERE / "config.json"
OUT_DIR = HERE.parent / "docs" / "sensors" / "data"


def main():
    with open(CONFIG_PATH, encoding="utf-8") as f:
        config = json.load(f)

    now = datetime.now(timezone.utc)
    temp_readings, geo_readings = simulator.generate_backfill(config, now)
    sim_config = simulator.sim_config_payload(config)
    sim_config["generated_at"] = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    sim_config["is_snapshot"] = True

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    paths = {
        "sim_temperature.json": temp_readings,
        "sim_location.json": geo_readings,
        "sim_config.json": sim_config,
    }
    for name, payload in paths.items():
        out_path = OUT_DIR / name
        # Compact (no indent) for the two reading lists - thousands of rows,
        # generated not hand-edited, and pretty-printing roughly triples
        # their size for a static asset every visitor downloads. sim_config
        # is tiny either way, kept readable.
        indent = 2 if name == "sim_config.json" else None
        separators = None if indent else (",", ":")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=indent, separators=separators)
        print(f"  wrote: {out_path} ({len(payload) if isinstance(payload, list) else 1} row(s))")

    print(f"done -> {OUT_DIR} (snapshot as of {sim_config['generated_at']})")


if __name__ == "__main__":
    main()
