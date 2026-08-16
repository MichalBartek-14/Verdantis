"""
Per-client registry.

One JSON file per client under clients/ (see clients/_example.json.template
for the schema and clients/valice.json for a real one) holds everything
that varies plot-to-plot: shapefile path, alert bbox, per-client threshold
overrides, and the display metadata the published site personalizes with
(docs/c/<slug>/data/client_meta.json is generated from this by
publish_site.py - see there for how it reaches the browser).

Everything that does NOT vary per client - backend URL, collection id,
cloud-mask kernel sizes, monthly reducer, history window length, BFAST
seasonal period/penalty scale, and so on - stays in config.py exactly as
before. apply_client_overrides() only patches the handful of attributes
this schema defines, so utils/*.py (which reads straight from the config
module) needs no changes at all.

Every pipeline entry point takes a required --client <slug> argument; see
any of pilot_historical_analysis.py / drought_monitor_recent.py /
build_sector_explorer_data.py / bfast_alert.py's `if __name__ == "__main__"`
block for the (identical, three-line) wiring.
"""
import json
from pathlib import Path

CLIENTS_DIR = Path("clients")

REQUIRED_FIELDS = ["slug", "display_name", "location", "plot_shapefile", "alert_bbox"]


def list_clients() -> list:
    """Slugs of every configured client, sorted. Skips _example.json.template
    (leading underscore) and anything else that isn't a plain <slug>.json."""
    return sorted(
        p.stem for p in CLIENTS_DIR.glob("*.json") if not p.stem.startswith("_")
    )


def load_client(slug: str) -> dict:
    path = CLIENTS_DIR / f"{slug}.json"
    if not path.exists():
        known = ", ".join(list_clients()) or "(none configured yet)"
        raise FileNotFoundError(f"No client config at {path}. Known clients: {known}")

    data = json.loads(path.read_text())
    missing = [f for f in REQUIRED_FIELDS if not data.get(f)]
    if missing:
        raise ValueError(f"{path} is missing required field(s): {', '.join(missing)}")

    data.setdefault("client_name", data["display_name"])
    data.setdefault("plot_area_ha", None)
    data.setdefault("ndwi_dry_threshold", None)
    data.setdefault("ndmi_dry_threshold", None)
    data.setdefault("accent_color", "#2c7a3c")  # Verdantis green, the site's own default
    # Must match a docs/_template/assets/i18n/<language>/ folder - see
    # publish_site.py (writes this into client_meta.json) and
    # docs/_template/assets/client.js (reads it from there at page load).
    data.setdefault("language", "en")
    return data


def apply_client_overrides(config_module, client: dict) -> None:
    """Patch the per-plot attributes on an imported config module in place,
    and namespace OUTPUT_DIR under outputs/<slug> so two clients' runs -
    sequential or (carefully) concurrent - never share or overwrite each
    other's downloaded rasters."""
    config_module.PLOT_SHAPEFILE = Path(client["plot_shapefile"])
    config_module.ALERT_BBOX = client["alert_bbox"]
    if client.get("ndwi_dry_threshold") is not None:
        config_module.NDWI_DRY_THRESHOLD = client["ndwi_dry_threshold"]
    if client.get("ndmi_dry_threshold") is not None:
        config_module.NDMI_DRY_THRESHOLD = client["ndmi_dry_threshold"]
    config_module.OUTPUT_DIR = Path("outputs") / client["slug"]


def add_client_arg(parser) -> None:
    """Shared CLI wiring for every entry-point script:
        parser = argparse.ArgumentParser()
        clients.add_client_arg(parser)
        args = parser.parse_args()
        clients.apply_client_overrides(config, clients.load_client(args.client))
    """
    known = ", ".join(list_clients()) or "none configured yet - see clients/_example.json.template"
    parser.add_argument(
        "--client", required=True,
        help=f"Client slug under clients/<slug>.json. Configured: {known}",
    )
