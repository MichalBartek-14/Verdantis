"""
Recent drought-monitoring snapshot (precursor to a future alert product)
==========================================================================
Pulls the last RECENT_MONTHS of Sentinel-2 data over the client's plot at
a finer (weekly) compositing interval, computes NDVI/NDWI/NDMI, and writes
out a "current conditions" raster set + a small JSON summary.

This is intentionally lightweight - the goal is a data feed a future
alerting/thresholding layer can be built on top of (e.g. watch
pct_pixels_below_dry_threshold across runs and notify when it crosses a
limit), not a finished alert product.

Run:    python drought_monitor_recent.py
Setup:  edit config.py first (shapefile path, RECENT_MONTHS, thresholds).
"""
import json
from datetime import date

from dateutil.relativedelta import relativedelta

import config
from utils.plot_geometry import load_plot, get_bbox
from utils.openeo_client import connect
from utils.cloud_masking import build_cloud_mask, apply_cloud_mask
from utils.indices import ndvi_band, ndwi_band, ndmi_band, combine_as_bands
from utils.raster_analysis import open_cube, clip_to_geometry, TIME_DIM
from utils.plotting import plot_index_quicklook
from utils.downloads import download_to_path


def build_recent_index_cube(connection, bbox, temporal_extent):
    spatial_extent = {
        "west": bbox[0], "south": bbox[1], "east": bbox[2], "north": bbox[3],
        "crs": "EPSG:4326",
    }

    raw = connection.load_collection(
        config.COLLECTION_ID,
        spatial_extent=spatial_extent,
        temporal_extent=temporal_extent,
        bands=["B04", "B08", "B8A", "B11"],
        max_cloud_cover=config.MAX_CLOUD_COVER,
    )

    cloud_mask = build_cloud_mask(connection, bbox, temporal_extent)
    masked = apply_cloud_mask(raw, cloud_mask)

    indices = combine_as_bands(NDVI=ndvi_band(masked), NDWI=ndwi_band(masked), NDMI=ndmi_band(masked))
    composite = indices.aggregate_temporal_period(period=config.RECENT_PERIOD, reducer=config.MONTHLY_REDUCER)
    return composite


def export_recent_composites(ds_clipped, out_dir):
    """Write an NDVI + NDWI + NDMI PNG quicklook per composite date in the
    window (flat folder, date baked into each filename) so the whole
    RECENT_MONTHS window can be browsed week-by-week in a normal file
    explorer, instead of only ever seeing the latest snapshot. Fully
    cloud-masked composites (no valid pixels anywhere in the plot) are
    skipped. Set config.EXPORT_RECENT_GEOTIFF = True to also write a
    matching GeoTIFF triple per date for GIS-level analysis."""
    out_dir.mkdir(parents=True, exist_ok=True)
    written_dates = []

    for i in range(ds_clipped.sizes[TIME_DIM]):
        step = ds_clipped.isel({TIME_DIM: i})
        step_date = str(ds_clipped[TIME_DIM].values[i])[:10]

        if bool(step["NDVI"].isnull().all()) and bool(step["NDWI"].isnull().all()) and bool(step["NDMI"].isnull().all()):
            print(f"  Skipping {step_date} - fully cloud-masked, no valid pixels in the plot.")
            continue

        plot_index_quicklook(
            step["NDVI"].values, out_dir / f"ndvi_quicklook_{step_date}.png",
            cmap="RdYlGn", vmin=-0.1, vmax=1.0,
            title=f"NDVI - {step_date}", cbar_label="NDVI",
        )
        plot_index_quicklook(
            step["NDWI"].values, out_dir / f"ndwi_quicklook_{step_date}.png",
            cmap="BrBG", vmin=-0.3, vmax=0.3,
            title=f"NDWI - {step_date}", cbar_label="NDWI",
        )
        plot_index_quicklook(
            step["NDMI"].values, out_dir / f"ndmi_quicklook_{step_date}.png",
            cmap="BrBG", vmin=-0.3, vmax=0.3,
            title=f"NDMI - {step_date}", cbar_label="NDMI",
        )

        if config.EXPORT_RECENT_GEOTIFF:
            # .rio.to_raster() deletes-then-recreates an existing destination
            # in place, which hits the same Windows Search Indexer/Defender
            # file-lock race as a direct download does - route it through
            # download_to_path() too (see utils/downloads.py for why).
            download_to_path(lambda tmp, arr=step["NDVI"]: arr.rio.to_raster(tmp), out_dir / f"ndvi_{step_date}.tif")
            download_to_path(lambda tmp, arr=step["NDWI"]: arr.rio.to_raster(tmp), out_dir / f"ndwi_{step_date}.tif")
            download_to_path(lambda tmp, arr=step["NDMI"]: arr.rio.to_raster(tmp), out_dir / f"ndmi_{step_date}.tif")

        written_dates.append(step_date)

    return written_dates


def run_monitor():
    config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    plot_gdf = load_plot(config.PLOT_SHAPEFILE)
    bbox = get_bbox(plot_gdf, buffer_m=config.PLOT_BUFFER_M)

    end = date.today()
    start = end - relativedelta(months=config.RECENT_MONTHS)
    temporal_extent = [start.isoformat(), end.isoformat()]

    print(f"Connecting to {config.OPENEO_BACKEND_URL} ...")
    connection = connect(config.OPENEO_BACKEND_URL)

    print(f"Requesting {config.RECENT_PERIOD}ly composites for {temporal_extent[0]} to {temporal_extent[1]} ...")
    cube = build_recent_index_cube(connection, bbox, temporal_extent)

    out_netcdf = config.OUTPUT_DIR / "recent_ndvi_ndwi_ndmi.nc"
    # Small time/area window - a synchronous download is fine here, no
    # need for a batch job like the multi-year historical pilot uses.
    # Downloads via a temp file first - see utils/downloads.py for why.
    download_to_path(lambda tmp: cube.download(tmp, format="NetCDF"), out_netcdf)
    print(f"Downloaded: {out_netcdf}")

    ds = open_cube(out_netcdf)
    ds_clipped = clip_to_geometry(ds, plot_gdf)

    if ds_clipped.sizes.get(TIME_DIM, 0) == 0:
        print(
            "No usable (cloud-free) composite in the requested window - "
            "try a longer RECENT_MONTHS or a higher MAX_CLOUD_COVER in config.py."
        )
        return

    composites_dir = config.OUTPUT_DIR / "recent_composites"
    written_dates = export_recent_composites(ds_clipped, composites_dir)
    print(f"Per-date NDVI/NDWI/NDMI quicklooks saved for {len(written_dates)} dates under: {composites_dir}")

    latest = ds_clipped.isel({TIME_DIM: -1})
    latest_date = str(ds_clipped[TIME_DIM].values[-1])[:10]

    mean_ndvi = float(latest["NDVI"].mean(skipna=True))
    mean_ndwi = float(latest["NDWI"].mean(skipna=True))
    mean_ndmi = float(latest["NDMI"].mean(skipna=True))
    # "Dry" classification stays NDWI-based (the established convention
    # throughout this pilot) - NDMI is surfaced alongside it for
    # comparison, not as a second independent alert trigger.
    dry_mask = (latest["NDWI"] < config.NDWI_DRY_THRESHOLD) & latest["NDWI"].notnull()
    pct_dry_pixels = float(dry_mask.mean() * 100)

    # Via download_to_path() - see the EXPORT_RECENT_GEOTIFF block above for why.
    download_to_path(lambda tmp: latest["NDVI"].rio.to_raster(tmp), config.OUTPUT_DIR / f"ndvi_latest_{latest_date}.tif")
    download_to_path(lambda tmp: latest["NDWI"].rio.to_raster(tmp), config.OUTPUT_DIR / f"ndwi_latest_{latest_date}.tif")
    download_to_path(lambda tmp: latest["NDMI"].rio.to_raster(tmp), config.OUTPUT_DIR / f"ndmi_latest_{latest_date}.tif")

    summary = {
        "plot_shapefile": str(config.PLOT_SHAPEFILE),
        "composite_date": latest_date,
        "compositing_period": config.RECENT_PERIOD,
        "mean_ndvi": round(mean_ndvi, 3),
        "mean_ndwi": round(mean_ndwi, 3),
        "mean_ndmi": round(mean_ndmi, 3),
        "pct_pixels_below_dry_threshold": round(pct_dry_pixels, 1),
        "ndwi_dry_threshold": config.NDWI_DRY_THRESHOLD,
        "note": "Pilot/precursor output - thresholds not yet calibrated against field data.",
    }
    summary_path = config.OUTPUT_DIR / f"drought_summary_{latest_date}.json"
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)

    print(json.dumps(summary, indent=2))
    print(f"\nSummary saved: {summary_path}")


if __name__ == "__main__":
    run_monitor()
