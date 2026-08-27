"""
Renders a client's true-color satellite GeoTIFF into a lightweight PNG for
the site's title page hero (docs/_template/index.html - the photo sits
next to the title, see assets/style.css's .hero-image rules) AND records
that GeoTIFF's own geographic extent, reprojected to WGS84, as
outputs/<slug>/true_color_bounds.json - the plot-location map further down
that same page (index.html's own inline <script>, not client.js) uses
those bounds to lay the PNG over OpenStreetMap with L.imageOverlay(), so
the photo lands exactly where the plot really is rather than at some
approximate/guessed box. The PNG itself carries no georeference
(plt.imsave strips it), which is why this is written out as a sidecar
file instead.

The GeoTIFF itself is produced by a separate process outside this
pipeline (not by any script here) and is expected to already be cropped/
composited to the client's plot in the SAME CRS as that client's
shapefile - this script does no reprojection or clipping, it only turns
whatever raster it's given into a web-displayable image.

Source discovery: by default, the first *.tif/*.tiff file found next to
the client's shapefile (data/<slug>/) is used - no config needed, so
dropping the finished GeoTIFF into that folder and re-running this script
is the entire workflow. Set "true_color_tif" in clients/<slug>.json only
if a client's data folder ever holds more than one GeoTIFF and
auto-discovery would be ambiguous.

Safe to run before the GeoTIFF exists: this is explicitly meant to be run
repeatedly while the imagery is still being produced elsewhere - a
missing file is reported and skipped (exit 0), not an error, so it can
sit in a normal pipeline run without breaking anything. The site's hero
already reserves the layout space either way (see .hero-image's
placeholder state in index.html) - running this script just fills it in
once there's something to show.

Run:    python render_true_color.py --client <slug>
        python render_true_color.py --all
"""
import argparse
import json
from pathlib import Path

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.warp import transform_bounds

import clients

MAX_DIM = 1600  # cap the long edge so the hero photo stays a light web asset,
                 # regardless of the source GeoTIFF's native resolution


def find_true_color_tif(client: dict) -> Path | None:
    configured = client.get("true_color_tif")
    if configured:
        return Path(configured)

    data_dir = Path(client["plot_shapefile"]).parent
    candidates = sorted(data_dir.glob("*.tif")) + sorted(data_dir.glob("*.tiff"))
    if not candidates:
        return None
    if len(candidates) > 1:
        print(f"  note: {len(candidates)} GeoTIFFs found in {data_dir}, using {candidates[0].name} - "
              f"set \"true_color_tif\" in clients/{client['slug']}.json to pick a specific one.")
    return candidates[0]


def _stretch(band: np.ndarray, low=2.0, high=98.0) -> np.ndarray:
    """Percentile contrast stretch, per band - the standard "true color
    quicklook" treatment. Satellite reflectance values (whatever their
    native scale - 0-1 float, 0-10000 Sentinel-2 DN, already-0-255 uint8,
    ...) rarely span their theoretical full range in any single scene, so
    a naive min/max or fixed-divisor scale tends to look washed out or too
    dark. Works on whatever dtype/range is handed in without needing to
    know the source convention."""
    valid = band[np.isfinite(band)]
    if valid.size == 0:
        return np.zeros_like(band, dtype="float32")
    lo, hi = np.percentile(valid, [low, high])
    if hi <= lo:
        return np.zeros_like(band, dtype="float32")
    return np.clip((band - lo) / (hi - lo), 0, 1)


def render(client: dict) -> Path | None:
    slug = client["slug"]
    tif_path = find_true_color_tif(client)
    if tif_path is None:
        print(f"  no GeoTIFF yet for {slug} (looked in {Path(client['plot_shapefile']).parent}/) - "
              f"skipping, hero stays on its placeholder for now.")
        return None
    if not tif_path.exists():
        print(f"  {tif_path} (configured true_color_tif) not found yet - skipping.")
        return None

    with rasterio.open(tif_path) as src:
        n_bands = min(src.count, 3)
        scale = min(1.0, MAX_DIM / max(src.width, src.height))
        out_shape = (n_bands, max(1, round(src.height * scale)), max(1, round(src.width * scale)))
        bands = src.read(
            list(range(1, n_bands + 1)),
            out_shape=out_shape,
            resampling=Resampling.average,
        ).astype("float32")
        if src.nodata is not None:
            bands[bands == src.nodata] = np.nan
        # densify_pts=21 samples points along each edge before reprojecting,
        # not just the four corners - the safe way to get a WGS84 bounding
        # box for a source CRS whose grid isn't axis-aligned with lat/lon
        # (a plain per-corner reproject can under-cover the true extent).
        west, south, east, north = transform_bounds(src.crs, "EPSG:4326", *src.bounds, densify_pts=21)

    if n_bands == 1:
        # Single-band source (e.g. panchromatic) - show as grayscale rather
        # than fail; a real 3-band true-color composite is the expected case.
        rgb = np.repeat(_stretch(bands[0])[..., None], 3, axis=2)
    else:
        rgb = np.dstack([_stretch(bands[i]) for i in range(n_bands)])

    out_dir = Path("outputs") / slug
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "true_color.png"

    import matplotlib.pyplot as plt  # imported here, not at module level - this script's only
                                       # matplotlib use, and the import is slow enough to skip
                                       # when render() bails out early above (no GeoTIFF yet)
    plt.imsave(out_path, rgb)
    print(f"  saved: {out_path} ({rgb.shape[1]}x{rgb.shape[0]}, from {tif_path})")

    bounds_path = out_dir / "true_color_bounds.json"
    with open(bounds_path, "w") as f:
        json.dump({"west": west, "south": south, "east": east, "north": north}, f, indent=2)
    print(f"  saved: {bounds_path} (WGS84 extent, for the plot-location map)")
    return out_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--client", help="Render a single client slug.")
    group.add_argument("--all", action="store_true", help="Render every client in clients/.")
    args = parser.parse_args()

    slugs = clients.list_clients() if args.all else [args.client]
    for slug in slugs:
        print(f"=== {slug} ===")
        render(clients.load_client(slug))
