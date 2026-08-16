"""
One-off data-prep step for the interactive sector explorer artifact.
Reuses the already-downloaded historical cube
(outputs/monthly_ndvi_ndwi_ndmi.nc) and the already-fetched ERA5 monthly
series (outputs/{ndwi,ndmi}_temperature_monthly.csv) - no new network
calls. Aggregates the clipped pixel grid into 5x5-pixel sectors (partial
sectors at the bbox edges), computes each sector's series + dryness
frequency/magnitude + correlation with temperature for BOTH NDWI and
NDMI, each over the full 5-year history and over just the last
LAST_YEAR_MONTHS months, so the artifact can offer an index toggle
(NDWI/NDMI) on top of the existing "last year" option - without any new
download (same cube, just a different band). Writes everything as one
JSON payload for the HTML artifact to embed.
"""
import base64
import json
import math
import os
import tempfile
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

import config
from utils.plot_geometry import load_plot
from utils.plotting import plot_index_quicklook
from utils.raster_analysis import open_cube, clip_to_geometry, TIME_DIM

BLOCK = 5  # sector size in pixels (5x5); edge sectors are smaller, covering the full bbox
LAST_YEAR_MONTHS = 12  # window size for the "last year" option, in months

INDEX_THRESHOLDS = {"NDWI": config.NDWI_DRY_THRESHOLD, "NDMI": config.NDMI_DRY_THRESHOLD}


def _num_or_none(v, digits):
    # json.dump emits bare NaN/Infinity by default (a non-standard JSON
    # extension) that JS's JSON.parse then rejects outright as a syntax
    # error - route every float through here so gaps become proper JSON
    # null instead. (json.dump(..., allow_nan=False) below is the backstop
    # in case any value slips past this.)
    return None if pd.isna(v) else round(float(v), digits)


def window_stats(values, era5_vals, threshold):
    """Dryness frequency/magnitude/mean/correlation over one window (full
    history or the last-year slice) of a single sector's or the whole
    plot's monthly series for one index - same math regardless of which
    index or window is fed in."""
    values = np.asarray(values, dtype=float)
    valid_mask = ~np.isnan(values)
    n_valid = int(valid_mask.sum())
    dry_mask = valid_mask & (values < threshold)
    n_dry = int(dry_mask.sum())

    freq_pct = round(100.0 * n_dry / n_valid, 1) if n_valid else None
    magnitude = round(float(np.mean(threshold - values[dry_mask])), 4) if n_dry else (0.0 if n_valid else None)
    mean_val = round(float(np.nanmean(values)), 4) if n_valid else None

    pairs = [(v, t) for v, t, m in zip(values, era5_vals, valid_mask) if m and t is not None]
    corr = None
    if len(pairs) >= 3:
        v_arr = np.array([p[0] for p in pairs])
        t_arr = np.array([p[1] for p in pairs])
        if v_arr.std() > 0 and t_arr.std() > 0:
            corr = round(float(np.corrcoef(v_arr, t_arr)[0, 1]), 3)

    return {"n_valid_months": n_valid, "freq_pct": freq_pct, "magnitude": magnitude, "mean": mean_val, "corr": corr}


def png_data_uri(array, cmap, vmin, vmax, title, cbar_label):
    """Render one whole-plot index composite via the existing
    plot_index_quicklook() (unmodified - reused exactly as
    drought_monitor_recent.py's per-date export uses it) into a temp
    file, then inline it as a base64 data: URI so the artifact stays a
    single self-contained HTML file with no external image files."""
    fd, tmp_name = tempfile.mkstemp(suffix=".png")
    os.close(fd)  # Windows won't allow deleting a file with an open handle - close it first
    tmp_path = Path(tmp_name)
    try:
        plot_index_quicklook(array, tmp_path, cmap=cmap, vmin=vmin, vmax=vmax, title=title, cbar_label=cbar_label)
        return "data:image/png;base64," + base64.b64encode(tmp_path.read_bytes()).decode("ascii")
    finally:
        tmp_path.unlink(missing_ok=True)


ds = open_cube("outputs/monthly_ndvi_ndwi_ndmi.nc")
plot_gdf = load_plot(config.PLOT_SHAPEFILE)
ds_clipped = clip_to_geometry(ds, plot_gdf)

n_t, n_y, n_x = ds_clipped["NDWI"].values.shape
months = [str(m)[:7] for m in ds_clipped[TIME_DIM].values]

n_rows = math.ceil(n_y / BLOCK)
n_cols = math.ceil(n_x / BLOCK)

era5 = pd.read_csv("outputs/era5_temperature_monthly.csv", parse_dates=["month"])
era5_by_month = dict(zip(era5["month"].dt.strftime("%Y-%m"), era5["mean_temp_c"]))
era5_series = [era5_by_month.get(m) for m in months]


def build_index_payload(variable, threshold):
    """Per-sector + whole-plot stats for one moisture index (NDWI or
    NDMI), both full-history and last-year windows. The same computation
    either variable is fed through, looped once per index rather than
    hand-duplicated."""
    values_full = ds_clipped[variable].values  # (t, y, x)

    sectors = []
    for row in range(n_rows):
        y0, y1 = row * BLOCK, min((row + 1) * BLOCK, n_y)
        for col in range(n_cols):
            x0, x1 = col * BLOCK, min((col + 1) * BLOCK, n_x)
            block = values_full[:, y0:y1, x0:x1]
            n_pixels = block.shape[1] * block.shape[2]

            # Some months have zero valid pixels in a given sector (cloud-masked
            # or the sector sits mostly/entirely outside the plot polygon) -
            # nanmean over an all-NaN slice correctly yields NaN but warns; the
            # NaN is handled explicitly below via window_stats, so silence it.
            with warnings.catch_warnings(), np.errstate(invalid="ignore"):
                warnings.simplefilter("ignore", category=RuntimeWarning)
                monthly_mean = np.nanmean(block.reshape(n_t, -1), axis=1)
            if not np.isfinite(block).any():
                continue

            full = window_stats(monthly_mean, era5_series, threshold)
            last_year = window_stats(monthly_mean[-LAST_YEAR_MONTHS:], era5_series[-LAST_YEAR_MONTHS:], threshold)

            sectors.append({
                "row": row,
                "col": col,
                "n_pixels": n_pixels,
                "series": [_num_or_none(v, 4) for v in monthly_mean],
                **full,
                "freq_pct_1y": last_year["freq_pct"],
                "magnitude_1y": last_year["magnitude"],
                "mean_1y": last_year["mean"],
                "corr_1y": last_year["corr"],
                "n_valid_months_1y": last_year["n_valid_months"],
            })

    # Whole-plot summary - reuses the already-computed plot-average series
    # from pilot_historical_analysis.py's <index>_temperature_monthly.csv.
    plot_ts = pd.read_csv(f"outputs/{variable.lower()}_temperature_monthly.csv", parse_dates=["month"])
    mean_col = f"mean_{variable.lower()}"
    plot_full = window_stats(plot_ts[mean_col].values, plot_ts["mean_temp_c"].values, threshold)
    plot_last_year = window_stats(
        plot_ts[mean_col].values[-LAST_YEAR_MONTHS:], plot_ts["mean_temp_c"].values[-LAST_YEAR_MONTHS:], threshold
    )
    plot_summary = {
        "series": [_num_or_none(v, 4) for v in plot_ts[mean_col]],
        **plot_full,
        "freq_pct_1y": plot_last_year["freq_pct"],
        "magnitude_1y": plot_last_year["magnitude"],
        "mean_1y": plot_last_year["mean"],
        "corr_1y": plot_last_year["corr"],
        "n_valid_months_1y": plot_last_year["n_valid_months"],
    }

    return {"threshold": threshold, "sectors": sectors, "plot_summary": plot_summary}


indices_payload = {
    variable.lower(): build_index_payload(variable, threshold)
    for variable, threshold in INDEX_THRESHOLDS.items()
}

# Whole-plot NDVI/NDWI/NDMI quicklook images for the last-year window, for
# the "Monthly Imagery" tab - same 12 months as the sector explorer's
# "Last year" option, same colormap conventions as the recent-monitor
# script's per-date quicklooks (utils/plotting.py).
print("Rendering monthly imagery (NDVI + NDWI + NDMI quicklooks, last-year window) ...")
imagery_months = months[-LAST_YEAR_MONTHS:]
imagery = {"months": imagery_months, "ndvi": [], "ndwi": [], "ndmi": []}
for i in range(n_t - LAST_YEAR_MONTHS, n_t):
    m = months[i]
    imagery["ndvi"].append(png_data_uri(ds_clipped["NDVI"].values[i], "RdYlGn", -0.1, 1.0, f"NDVI - {m}", "NDVI"))
    imagery["ndwi"].append(png_data_uri(ds_clipped["NDWI"].values[i], "BrBG", -0.3, 0.3, f"NDWI - {m}", "NDWI"))
    imagery["ndmi"].append(png_data_uri(ds_clipped["NDMI"].values[i], "BrBG", -0.3, 0.3, f"NDMI - {m}", "NDMI"))

payload = {
    "grid": {"rows": n_rows, "cols": n_cols, "block": BLOCK, "y_size": n_y, "x_size": n_x},
    "months": months,
    "temp": [_num_or_none(t, 2) for t in era5_series],
    "last_year_months": LAST_YEAR_MONTHS,
    "indices": indices_payload,
    "imagery": imagery,
}

out_path = config.OUTPUT_DIR / "sector_explorer_data.json"
with open(out_path, "w") as f:
    # allow_nan=False: fail loudly here at generation time if a NaN/Infinity
    # ever slips through, rather than shipping invalid JSON that only breaks
    # much later inside the browser's JSON.parse.
    json.dump(payload, f, allow_nan=False)

for key, idx_payload in indices_payload.items():
    print(f"{key.upper()} sectors with data: {len(idx_payload['sectors'])} / {n_rows * n_cols} grid cells")
print(f"Months: {len(months)} ({months[0]} to {months[-1]})")
print(f"Imagery: {len(imagery['ndvi'])} NDVI + {len(imagery['ndwi'])} NDWI + {len(imagery['ndmi'])} NDMI "
      f"quicklooks ({imagery_months[0]} to {imagery_months[-1]})")
print(f"Saved: {out_path} ({out_path.stat().st_size / 1024:.1f} KB)")
