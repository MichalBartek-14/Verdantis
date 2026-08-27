"""
Per-client registry.

One JSON file per client under clients/ (see clients/_example.json.template
for the schema and clients/valice.json for a real one) holds everything
that varies plot-to-plot: shapefile path, alert bbox, per-client threshold
overrides, the display metadata the published site personalizes with
(docs/c/<slug>/data/client_meta.json is generated from this by
publish_site.py - see there for how it reaches the browser), and optional
per-client site-copy tweaks (i18n_overrides - see load_client() below).

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

    # encoding="utf-8" is NOT the default for Path.read_text() - it falls
    # back to the platform's preferred encoding, which on Windows is
    # typically cp1252, silently mangling any non-ASCII character (e.g. a
    # Slovak client_name/location, or non-English i18n_overrides text)
    # into mojibake instead of raising an error you'd actually notice.
    data = json.loads(path.read_text(encoding="utf-8"))
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
    # Optional true-color satellite GeoTIFF for the title page hero - see
    # render_true_color.py. Leave null/omitted to auto-discover the first
    # *.tif/*.tiff next to the shapefile (data/<slug>/) - only set this
    # explicitly if a client's folder ever holds more than one GeoTIFF and
    # auto-discovery would be ambiguous.
    data.setdefault("true_color_tif", None)
    # Optional per-client wording tweaks, applied by publish_site.py AFTER
    # it copies the shared docs/_template/assets/i18n/<lang>/ dictionaries -
    # for when the shared template's phrasing doesn't fit one specific
    # client (e.g. a forest plot vs. a fruit orchard) but isn't wrong
    # enough to change for everyone. Shape mirrors the i18n JSON files
    # themselves: {"<language>": {"<page>": {...same nested keys...}}} -
    # only include the keys you want to override, everything else still
    # comes from the template. See clients/_example.json.template for a
    # worked example. NEVER hand-edit docs/c/<slug>/assets/i18n/ directly -
    # publish_site.py overwrites it from scratch (template + these
    # overrides) on every run, so a direct edit there is silently lost the
    # next time anyone republishes.
    data.setdefault("i18n_overrides", {})
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
