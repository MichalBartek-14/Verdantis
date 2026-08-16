"""
Vegetation-break alert branch (BFAST-style)
=============================================
A separate, parallel product to the plot/sector moisture monitoring: point
it at ANY bounding box (not necessarily the client plot - set ALERT_BBOX in
config.py) and it pulls every available raw Sentinel-2 scene over that area
(no monthly/weekly compositing - the actual per-acquisition NDVI values),
plots the resulting irregular time series, and flags likely structural
breaks - a harvest, dieback, storm damage, land-use change - using a
BFAST-style decomposition + changepoint search.

Not the literal bfast/R package or its GPU-accelerated Python port (`bfast`
on PyPI hard-requires pyopencl and a working OpenCL runtime - impractical to
depend on for a pilot script). This reuses the same underlying idea BFAST
(Verbesselt et al.) is built on - decompose the series into trend + season +
remainder, then test the trend for structural breaks - using two
well-supported, GPU-free libraries: statsmodels' STL decomposition and
ruptures' PELT changepoint search.

Run:    python bfast_alert.py
Setup:  edit config.py first - ALERT_BBOX (defaults to the client plot's
        own bbox), ALERT_YEARS, BFAST_PENALTY_SCALE.
"""
import json
import warnings
from datetime import date

import numpy as np
import pandas as pd
import ruptures as rpt
from dateutil.relativedelta import relativedelta
from statsmodels.tsa.seasonal import STL

import config
from utils.cloud_masking import build_cloud_mask, apply_cloud_mask
from utils.downloads import download_to_path
from utils.indices import ndvi_band
from utils.openeo_client import connect
from utils.plotting import plot_bfast_breaks
from utils.raster_analysis import open_cube, TIME_DIM

MIN_USABLE_SCENES = 8  # below this, break detection isn't meaningful


def build_raw_ndvi_cube(connection, bbox, temporal_extent):
    """Per-scene NDVI cube - deliberately NOT aggregate_temporal_period()'d,
    so every available cloud-masked acquisition survives individually,
    unlike every other script in this project which composites first."""
    spatial_extent = {"west": bbox[0], "south": bbox[1], "east": bbox[2], "north": bbox[3], "crs": "EPSG:4326"}
    raw = connection.load_collection(
        config.COLLECTION_ID, spatial_extent=spatial_extent, temporal_extent=temporal_extent,
        bands=["B04", "B08"], max_cloud_cover=config.MAX_CLOUD_COVER,
    )
    cloud_mask = build_cloud_mask(connection, bbox, temporal_extent)
    masked = apply_cloud_mask(raw, cloud_mask)
    # Re-attach a band label (band-math collapses it) so the downloaded
    # NetCDF has a named "NDVI" variable, matching every other script's
    # convention - see utils/indices.py's combine_as_bands for the same trick.
    return ndvi_band(masked).add_dimension(name="bands", label="NDVI", type="bands")


def run_alert():
    if not config.ALERT_BBOX:
        raise SystemExit("Set ALERT_BBOX in config.py first - [west, south, east, north] in EPSG:4326.")
    config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    bbox = config.ALERT_BBOX

    out_netcdf = config.OUTPUT_DIR / "alert_raw_ndvi.nc"
    if out_netcdf.exists():
        # Re-running just to retune BFAST_PENALTY_SCALE (or anything else
        # downstream of the download) shouldn't cost another multi-minute
        # batch job against an unchanged bbox/date-range - delete this file
        # to force a fresh pull (e.g. once new scenes have become available).
        print(f"Reusing already-downloaded {out_netcdf} (delete it to force a fresh pull).")
    else:
        end = date.today()
        start = end - relativedelta(years=config.ALERT_YEARS)
        temporal_extent = [start.isoformat(), end.isoformat()]

        print(f"Connecting to {config.OPENEO_BACKEND_URL} ...")
        connection = connect(config.OPENEO_BACKEND_URL)

        print(f"Requesting every available Sentinel-2 scene for {temporal_extent[0]} to {temporal_extent[1]} "
              f"over bbox {bbox} (no temporal compositing) ...")
        ndvi_cube = build_raw_ndvi_cube(connection, bbox, temporal_extent)

        print("Submitting batch job (per-scene requests over a multi-year window can take a while)...")
        job = ndvi_cube.create_job(out_format="NetCDF", title="forestry_alert_raw_ndvi")
        job.start_and_wait()
        # Downloads via a temp file first - see utils/downloads.py for why.
        download_to_path(lambda tmp: job.get_results().download_file(tmp), out_netcdf)
        print(f"Downloaded: {out_netcdf}")

    ds = open_cube(out_netcdf)
    ndvi = ds["NDVI"].values  # (t, y, x) - every scene, not clipped to any polygon (bbox IS the area of interest)
    dates = pd.to_datetime(ds[TIME_DIM].values)

    # Some scenes are fully cloud-masked over this bbox (zero valid pixels) -
    # nanmean over an all-NaN row correctly yields NaN but warns; handled
    # explicitly below via dropna(), so silence it.
    with warnings.catch_warnings(), np.errstate(invalid="ignore"):
        warnings.simplefilter("ignore", category=RuntimeWarning)
        scene_means = np.nanmean(ndvi.reshape(ndvi.shape[0], -1), axis=1)

    raw_series = pd.Series(scene_means, index=dates).dropna()
    # Collapse same-day duplicate acquisitions (adjacent-tile overlap) by averaging.
    raw_series = raw_series.groupby(raw_series.index.normalize()).mean().sort_index()

    raw_csv = config.OUTPUT_DIR / "alert_ndvi_raw.csv"
    raw_series.rename("mean_ndvi").to_csv(raw_csv, header=True, index_label="date")
    print(f"Raw per-scene NDVI saved: {raw_csv} ({len(raw_series)} usable scenes)")

    if len(raw_series) < MIN_USABLE_SCENES:
        print(f"Only {len(raw_series)} usable scenes (need >= {MIN_USABLE_SCENES}) - too few for reliable "
              f"break detection. Try a larger ALERT_BBOX, longer ALERT_YEARS, or a higher MAX_CLOUD_COVER.")
        return

    # Regularise onto a monthly grid (linear interpolation across cloud
    # gaps) so STL has the fixed-frequency series it needs - the same
    # irregular -> regular step bfast's own bfastts() does in the R package.
    monthly_index = pd.date_range(
        raw_series.index.min().to_period("M").to_timestamp(),
        raw_series.index.max().to_period("M").to_timestamp(),
        freq="MS",
    )
    if len(monthly_index) < 2 * config.BFAST_SEASONAL_PERIOD:
        print(f"Only {len(monthly_index)} months of coverage (need >= {2 * config.BFAST_SEASONAL_PERIOD} for "
              f"STL with a {config.BFAST_SEASONAL_PERIOD}-month season) - too short for reliable break "
              f"detection. Try a longer ALERT_YEARS.")
        return

    combined_index = raw_series.index.union(monthly_index)
    regular = raw_series.reindex(combined_index).interpolate("time", limit_direction="both").reindex(monthly_index)

    stl = STL(regular, period=config.BFAST_SEASONAL_PERIOD, robust=True).fit()
    trend = stl.trend

    # BIC-style penalty (Killick et al. 2012) scaled to this trend's own
    # variance - see config.BFAST_PENALTY_SCALE for why not a fixed number.
    penalty = max(config.BFAST_PENALTY_SCALE * float(trend.values.var()) * np.log(len(trend)), 1e-9)
    algo = rpt.Pelt(model="l2", jump=1, min_size=3).fit(trend.values.reshape(-1, 1))
    break_positions = algo.predict(pen=penalty)[:-1]  # drop the trailing end-of-series sentinel
    break_dates = [monthly_index[i] for i in break_positions]

    breaks = []
    for i, bd in zip(break_positions, break_dates):
        before = float(trend.values[max(0, i - 3):i].mean()) if i > 0 else float(trend.values[0])
        after = float(trend.values[i:i + 3].mean())
        breaks.append({
            "date": bd.strftime("%Y-%m-%d"),
            "trend_before": round(before, 4),
            "trend_after": round(after, 4),
            "delta": round(after - before, 4),
        })

    # ---------- history-length view: full window + a "last year" zoom -----
    # STL(period=12) needs >= 2 full seasonal cycles to decompose meaningfully
    # (guarded above), so a literal 1-year *recomputation* would be invalid -
    # there just isn't enough data for STL to separate trend from season on
    # its own. Instead, both views share the ONE trend/break computation
    # above (fit on the full ALERT_YEARS history) and the "1y" view is a
    # display-only window into it: the same trend line and only the breaks
    # that fall in the last 12 months, scoped for a closer look at recent
    # activity - not a second, shorter-and-shakier model.
    def window_view(years):
        """years=None -> full history, unfiltered. Otherwise everything
        (raw scatter, trend line, breaks) clipped to the last `years`
        years of the same fit above."""
        if years is None:
            return raw_series, monthly_index, trend.values, break_dates, breaks
        cutoff = monthly_index.max() - relativedelta(years=years)
        w_raw = raw_series[raw_series.index >= cutoff]
        w_mask = monthly_index >= cutoff
        w_index = monthly_index[w_mask]
        w_trend = trend.values[w_mask]
        w_breaks = [b for b in breaks if pd.Timestamp(b["date"]) >= cutoff]
        w_break_dates = [bd for bd in break_dates if bd >= cutoff]
        return w_raw, w_index, w_trend, w_break_dates, w_breaks

    full_label = f"{config.ALERT_YEARS}y"
    windows_spec = [(full_label, None, "Full history"), ("1y", 1, "Last year")]

    windows_json = {}
    for key, years, label in windows_spec:
        w_raw, w_index, w_trend, w_break_dates, w_breaks = window_view(years)
        windows_json[key] = {
            "label": label,
            "years": years if years is not None else config.ALERT_YEARS,
            "n_scenes": len(w_raw),
            "breaks": w_breaks,
        }
        suffix = "" if key == full_label else f"_{key}"
        plot_path = config.OUTPUT_DIR / f"alert_ndvi_breaks{suffix}.png"
        plot_bfast_breaks(
            w_raw, w_index, w_trend, w_break_dates, plot_path,
            title=f"NDVI - {label.lower()}, with detected structural breaks",
        )
        print(f"Chart saved ({label}): {plot_path}")

    breaks_path = config.OUTPUT_DIR / "alert_breaks.json"
    with open(breaks_path, "w") as f:
        json.dump({
            "bbox": bbox,
            "years_requested": config.ALERT_YEARS,
            "seasonal_period_months": config.BFAST_SEASONAL_PERIOD,
            "penalty_scale": config.BFAST_PENALTY_SCALE,
            "penalty_used": round(penalty, 6),
            "n_scenes": len(raw_series),
            "breaks": breaks,
            "default_window": full_label,
            "windows": windows_json,
        }, f, indent=2)
    print(f"Detected {len(breaks)} break(s) over the full {config.ALERT_YEARS}y history: {[b['date'] for b in breaks]}")
    print(f"  of which {len(windows_json['1y']['breaks'])} fall in the last year")
    print(f"Breaks saved: {breaks_path}")

    print("\nAlert run complete. Outputs in:", config.OUTPUT_DIR.resolve())


if __name__ == "__main__":
    run_alert()
