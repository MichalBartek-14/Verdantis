"""
Publish step for the Verdantis static site (docs/).

This is the ONLY link between the local backend and the public site: run
it by hand whenever you want the site to reflect a fresh pipeline run
(after pilot_historical_analysis.py / drought_monitor_recent.py /
build_sector_explorer_data.py / bfast_alert.py), then commit + push
docs/. The published pages never call openEO or talk to this machine -
they only read the already-computed files this script copies over, so
the site stays a plain static deploy (GitHub Pages, Netlify, ...) with
no backend to host or secure.

Run:    python publish_site.py
"""
import shutil
from pathlib import Path

import config

DOCS = Path("docs")
IMG = DOCS / "assets" / "img"
DATA = DOCS / "data"
RECENT_IMG = IMG / "recent"

# Historical pilot charts/maps referenced by docs/historical.html -
# copied as-is, they're already client-ready PNGs.
HISTORICAL_IMAGES = [
    "ndvi_timeseries.png",
    "ndwi_timeseries.png",
    "ndmi_timeseries.png",
    "dryness_heatmap.png",
    "water_loss_map.png",
    "water_loss_map_ndmi.png",
    "ndwi_temperature_combo.png",
]

# Alert chart referenced by docs/alerts.html.
ALERT_IMAGES = ["alert_ndvi_breaks.png"]


def _copy(name, dest_dir):
    src = config.OUTPUT_DIR / name
    if not src.exists():
        return False
    dest_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest_dir / name)
    return True


def publish_historical():
    print("Historical pilot images:")
    for name in HISTORICAL_IMAGES:
        ok = _copy(name, IMG)
        print(f"  {'copied' if ok else 'MISSING (run pilot_historical_analysis.py)'}: {name}")


def publish_alerts():
    print("Alert chart + breaks:")
    for name in ALERT_IMAGES:
        ok = _copy(name, IMG)
        print(f"  {'copied' if ok else 'MISSING (run bfast_alert.py)'}: {name}")

    breaks_src = config.OUTPUT_DIR / "alert_breaks.json"
    if breaks_src.exists():
        DATA.mkdir(parents=True, exist_ok=True)
        shutil.copy2(breaks_src, DATA / "alert_breaks.json")
        print("  copied: alert_breaks.json")
    else:
        print("  MISSING (run bfast_alert.py): alert_breaks.json")


def publish_recent():
    """Copies the newest drought_summary_*.json (by filename, which is
    date-stamped) to a fixed data/drought_summary_latest.json name so
    docs/recent.html's fetch() doesn't need to know today's date, plus
    its matching NDVI/NDWI/NDMI quicklook triple from recent_composites/."""
    print("Recent drought monitor:")
    summaries = sorted(config.OUTPUT_DIR.glob("drought_summary_*.json"))
    if not summaries:
        print("  MISSING (run drought_monitor_recent.py): no drought_summary_*.json")
        return
    latest = summaries[-1]
    DATA.mkdir(parents=True, exist_ok=True)
    shutil.copy2(latest, DATA / "drought_summary_latest.json")
    print(f"  copied: {latest.name} -> data/drought_summary_latest.json")

    latest_date = latest.stem.replace("drought_summary_", "")
    recent_dir = config.OUTPUT_DIR / "recent_composites"
    RECENT_IMG.mkdir(parents=True, exist_ok=True)
    copied = 0
    for index_name in ("ndvi", "ndwi", "ndmi"):
        src = recent_dir / f"{index_name}_quicklook_{latest_date}.png"
        if src.exists():
            shutil.copy2(src, RECENT_IMG / src.name)
            copied += 1
    print(f"  copied {copied}/3 latest quicklook(s) for {latest_date}")


def publish_explorer():
    """The interactive sector explorer is already a self-contained HTML
    file (base64-inlined images/JSON) - just drop it into docs/ as its
    own page instead of re-copying its data separately."""
    src = config.OUTPUT_DIR / "ndwi_era5_sector_explorer.html"
    if src.exists():
        shutil.copy2(src, DOCS / "explorer.html")
        print("Sector explorer: copied -> docs/explorer.html")
    else:
        print("Sector explorer: MISSING (run build_sector_explorer_data.py)")


if __name__ == "__main__":
    publish_historical()
    publish_alerts()
    publish_recent()
    publish_explorer()
    print("\nDone. Review docs/ locally, then `git add docs/` + commit + push to publish.")
