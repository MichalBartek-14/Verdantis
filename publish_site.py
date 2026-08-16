"""
Publish step for the Verdantis static site (docs/).

This is the ONLY link between the local backend and the public site: run
it by hand whenever you want a client's dashboard to reflect a fresh
pipeline run (after pilot_historical_analysis.py / drought_monitor_recent.py
/ build_sector_explorer_data.py / bfast_alert.py --client <slug>), then
commit + push docs/. The published pages never call openEO or talk to
this machine - they only read the already-computed files this script
writes into each client's docs/c/<slug>/assets and docs/c/<slug>/data, so
the site stays a plain static deploy (GitHub Pages, Netlify, ...) with no
backend to host or secure.

The site's HTML/CSS/JS (docs/_template/) is ONE hand-maintained template,
shared byte-for-byte across every client - this script copies it into
each docs/c/<slug>/ verbatim and never edits it. Only data + a handful of
images differ per client; see clients/README (clients.py's module
docstring) for the registry format and docs/_template/assets/client.js
for how the site personalizes itself from data/client_meta.json at
runtime (name, location, plot area, accent color).

Data isolation note: this repo is a SHARED codebase for every client (per
clients/*.json), but each client's docs/c/<slug>/ is meant to be deployed
- and access-controlled - independently (e.g. one Cloudflare Access rule
per /c/<slug>/* path, or one subdomain per client). Nothing here enforces
that at hosting time; it's a deploy/DNS/access-control decision, not code.

Run:
    python publish_site.py --client valice     # one client
    python publish_site.py --all                # every client in clients/
"""
import json
import shutil
from pathlib import Path

import clients

DOCS = Path("docs")
TEMPLATE = DOCS / "_template"
CLIENTS_ROOT = DOCS / "c"
CLIENTS_MANIFEST = DOCS / "clients.json"

# Historical pilot charts/maps referenced by _template/historical.html -
# copied as-is, they're already client-ready PNGs.
HISTORICAL_IMAGES = [
    "ndvi_timeseries.png",
    "ndwi_timeseries.png",
    "ndmi_timeseries.png",
    "dryness_heatmap.png",
    "water_loss_map.png",
    "water_loss_map_ndmi.png",
    "ndwi_temperature_combo.png",
    "ndwi_precipitation_combo.png",
]

# Alert charts referenced by _template/monitoring.html - one per history
# window (bfast_alert.py writes a full-history chart plus a "last year"
# zoom into the same fit; see its window_view() for why 1y isn't a
# separate model).
ALERT_IMAGES = ["alert_ndvi_breaks.png", "alert_ndvi_breaks_1y.png"]


def _copy(src_dir: Path, name: str, dest_dir: Path) -> bool:
    src = src_dir / name
    if not src.exists():
        return False
    dest_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest_dir / name)
    return True


def publish_client_site(slug: str) -> None:
    client = clients.load_client(slug)
    out = CLIENTS_ROOT / slug
    img = out / "assets" / "img"
    data = out / "data"
    outputs_dir = Path("outputs") / slug

    print(f"=== {slug} ({client['display_name']}) ===")

    language = client.get("language", "en")
    if not (TEMPLATE / "assets" / "i18n" / language).is_dir():
        available = sorted(p.name for p in (TEMPLATE / "assets" / "i18n").iterdir() if p.is_dir())
        raise SystemExit(
            f"clients/{slug}.json sets language=\"{language}\", but there's no "
            f"docs/_template/assets/i18n/{language}/ folder. Available: {', '.join(available)}."
        )

    # 1. Site shell - byte-identical template, re-copied every run so a
    #    template edit reaches every client on their next publish without
    #    needing per-client changes.
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(TEMPLATE, out)
    print(f"  template -> {out}/")

    # 2. Personalization metadata - the one file client.js reads (branding
    #    AND which i18n/<language>/ dictionary to load - see client.js).
    data.mkdir(parents=True, exist_ok=True)
    meta = {
        "slug": client["slug"],
        "display_name": client["display_name"],
        "client_name": client["client_name"],
        "location": client["location"],
        "plot_area_ha": client.get("plot_area_ha"),
        "accent_color": client.get("accent_color", "#2c7a3c"),
        "language": language,
    }
    with open(data / "client_meta.json", "w") as f:
        json.dump(meta, f, indent=2)
    print("  wrote: data/client_meta.json")

    # 3. Historical pilot images.
    print("  historical pilot images:")
    for name in HISTORICAL_IMAGES:
        ok = _copy(outputs_dir, name, img)
        print(f"    {'copied' if ok else 'MISSING (run pilot_historical_analysis.py --client ' + slug + ')'}: {name}")

    # 4. Alert charts + breaks.
    print("  alert charts + breaks:")
    for name in ALERT_IMAGES:
        ok = _copy(outputs_dir, name, img)
        print(f"    {'copied' if ok else 'MISSING (run bfast_alert.py --client ' + slug + ')'}: {name}")
    if _copy(outputs_dir, "alert_breaks.json", data):
        print("    copied: alert_breaks.json")
    else:
        print(f"    MISSING (run bfast_alert.py --client {slug}): alert_breaks.json")

    # 5. Recent drought monitor: newest drought_summary_*.json (filename is
    #    date-stamped) copied to a fixed name so monitoring.html's fetch()
    #    doesn't need to know today's date, plus its matching quicklook trio.
    print("  recent drought monitor:")
    summaries = sorted(outputs_dir.glob("drought_summary_*.json"))
    if not summaries:
        print(f"    MISSING (run drought_monitor_recent.py --client {slug}): no drought_summary_*.json")
    else:
        latest = summaries[-1]
        shutil.copy2(latest, data / "drought_summary_latest.json")
        print(f"    copied: {latest.name} -> data/drought_summary_latest.json")

        latest_date = latest.stem.replace("drought_summary_", "")
        recent_dir = outputs_dir / "recent_composites"
        recent_img = img / "recent"
        recent_img.mkdir(parents=True, exist_ok=True)
        copied = sum(
            _copy(recent_dir, f"{idx}_quicklook_{latest_date}.png", recent_img)
            for idx in ("ndvi", "ndwi", "ndmi")
        )
        print(f"    copied {copied}/3 latest quicklook(s) for {latest_date}")

    # 6. Sector explorer + monthly imagery data - imagery split off since
    #    it's ~80% of the payload's size and the sector map itself never
    #    reads it (see docs/_template/monitoring.html for the slider that does).
    print("  sector explorer + monthly imagery data:")
    src = outputs_dir / "sector_explorer_data.json"
    if not src.exists():
        print(f"    MISSING (run build_sector_explorer_data.py --client {slug}): sector_explorer_data.json")
    else:
        with open(src) as f:
            payload = json.load(f)
        imagery = payload.pop("imagery", None)
        with open(data / "sector_explorer_data.json", "w") as f:
            json.dump(payload, f, allow_nan=False)
        print(f"    wrote: data/sector_explorer_data.json ({(data / 'sector_explorer_data.json').stat().st_size / 1024:.0f} KB, imagery-free)")
        if imagery is not None:
            with open(data / "monthly_imagery.json", "w") as f:
                json.dump(imagery, f, allow_nan=False)
            print(f"    wrote: data/monthly_imagery.json ({(data / 'monthly_imagery.json').stat().st_size / 1024:.0f} KB)")

    print(f"  done -> {out}/index.html\n")


def update_manifest() -> None:
    """docs/clients.json - the root picker page's (docs/index.html) only
    data source. Rebuilt from the client registry filtered to whoever has
    actually been published (has a docs/c/<slug>/ folder), not just
    whoever's configured - so a client added to clients/ but never
    published doesn't show up as a dead link."""
    manifest = []
    for slug in clients.list_clients():
        if not (CLIENTS_ROOT / slug).exists():
            continue
        client = clients.load_client(slug)
        manifest.append({
            "slug": slug,
            "display_name": client["display_name"],
            "location": client["location"],
        })
    with open(CLIENTS_MANIFEST, "w") as f:
        json.dump(manifest, f, indent=2)
    print(f"Updated {CLIENTS_MANIFEST} ({len(manifest)} published client(s))")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--client", help="Publish a single client slug.")
    group.add_argument("--all", action="store_true", help="Publish every client in clients/.")
    args = parser.parse_args()

    slugs = clients.list_clients() if args.all else [args.client]
    if not slugs:
        raise SystemExit("No clients configured under clients/ - see clients/_example.json.template.")

    for slug in slugs:
        publish_client_site(slug)
    update_manifest()

    print("Review docs/ locally, then `git add docs/` + commit + push to publish.")
