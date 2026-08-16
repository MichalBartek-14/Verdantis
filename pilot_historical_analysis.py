"""
Forestry monitoring pilot - historical analysis
=================================================
Backbone script for the pilot deliverable shown to the client:

  1. Load the client's plot boundary (shapefile).
  2. Pull up to HISTORY_YEARS of monthly Sentinel-2 composites over the
     plot from the Copernicus Data Space Ecosystem via openEO.
  3. Compute NDVI + NDWI + NDMI server-side (keeps the download small -
     three index bands instead of the full reflectance stack).
  4. Locally: clip to the exact plot polygon and build
       - plot-average NDVI, NDWI, and NDMI time series charts
       - a two-panel "which sections run dry most often, and how badly"
         map (frequency + magnitude) for both NDWI and NDMI
       - ERA5-based (Open-Meteo archive, no API key needed) monthly
         temperature AND total precipitation for the same window, each
         merged against both moisture series for a printed correlation
         coefficient (combo charts for NDWI, since NDWI/NDMI track each
         other closely enough that a second near-identical chart
         wouldn't add much)

Run:    python pilot_historical_analysis.py
Setup:  edit config.py first (shapefile path, date range, thresholds).
"""
from datetime import date

import pandas as pd
from dateutil.relativedelta import relativedelta

import config
from utils.plot_geometry import load_plot, get_bbox
from utils.openeo_client import connect
from utils.cloud_masking import build_cloud_mask, apply_cloud_mask
from utils.indices import ndvi_band, ndwi_band, ndmi_band, combine_as_bands
from utils.raster_analysis import (
    open_cube, clip_to_geometry, monthly_mean_timeseries, dryness_frequency,
    dryness_deficit_magnitude, TIME_DIM,
)
from utils.plotting import (
    plot_ndvi_timeseries, plot_dryness_heatmap, plot_ndwi_timeseries,
    plot_ndmi_timeseries, plot_water_loss_map, plot_ndwi_temperature_combo,
    plot_ndwi_precipitation_combo,
)
from utils.downloads import download_to_path
from utils.weather import fetch_era5_monthly_temperature, fetch_era5_monthly_precipitation


def build_monthly_index_cube(connection, bbox, temporal_extent):
    """Assemble the openEO process graph: load -> cloud-mask -> indices
    -> monthly composite. Nothing here is executed until download()/
    create_job() is called - this just builds the process graph."""
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
    monthly = indices.aggregate_temporal_period(period="month", reducer=config.MONTHLY_REDUCER)
    return monthly


def run_pilot():
    config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    plot_gdf = load_plot(config.PLOT_SHAPEFILE)
    bbox = get_bbox(plot_gdf, buffer_m=config.PLOT_BUFFER_M)

    end = date.today().replace(day=1)
    start = end - relativedelta(years=config.HISTORY_YEARS)
    temporal_extent = [start.isoformat(), end.isoformat()]

    out_netcdf = config.OUTPUT_DIR / "monthly_ndvi_ndwi_ndmi.nc"
    if out_netcdf.exists():
        # Re-running just to retune a downstream threshold/plot shouldn't
        # cost another multi-minute batch job against an unchanged
        # plot/date-range - delete this file to force a fresh pull (e.g.
        # once new months have become available).
        print(f"Reusing already-downloaded {out_netcdf} (delete it to force a fresh pull).")
    else:
        print(f"Connecting to {config.OPENEO_BACKEND_URL} ...")
        connection = connect(config.OPENEO_BACKEND_URL)

        print(f"Building request for {temporal_extent[0]} to {temporal_extent[1]} ...")
        monthly_cube = build_monthly_index_cube(connection, bbox, temporal_extent)

        print("Submitting batch job (can take several minutes for multi-year requests)...")
        job = monthly_cube.create_job(out_format="NetCDF", title="forestry_pilot_monthly_indices")
        job.start_and_wait()
        # If the backend ever returns more than one output asset, use
        # job.get_results().download_files(config.OUTPUT_DIR) instead and
        # locate the .nc file there.
        # Downloads via a temp file first - see utils/downloads.py for why.
        download_to_path(lambda tmp: job.get_results().download_file(tmp), out_netcdf)
        print(f"Downloaded: {out_netcdf}")

    # --- local analysis --------------------------------------------------
    ds = open_cube(out_netcdf)
    ds_clipped = clip_to_geometry(ds, plot_gdf)

    ndvi_ts = monthly_mean_timeseries(ds_clipped, "NDVI")
    dates = pd.to_datetime(ndvi_ts[TIME_DIM].values)
    values = ndvi_ts.values

    ts_csv = config.OUTPUT_DIR / "ndvi_timeseries.csv"
    pd.DataFrame({"date": dates, "mean_ndvi": values}).to_csv(ts_csv, index=False)
    plot_ndvi_timeseries(dates, values, config.OUTPUT_DIR / "ndvi_timeseries.png")
    print(f"NDVI time series saved: {ts_csv}")

    ndwi_ts = monthly_mean_timeseries(ds_clipped, "NDWI")
    ndwi_dates = pd.to_datetime(ndwi_ts[TIME_DIM].values)
    ndwi_values = ndwi_ts.values

    ndwi_csv = config.OUTPUT_DIR / "ndwi_timeseries.csv"
    pd.DataFrame({"date": ndwi_dates, "mean_ndwi": ndwi_values}).to_csv(ndwi_csv, index=False)
    plot_ndwi_timeseries(ndwi_dates, ndwi_values, config.OUTPUT_DIR / "ndwi_timeseries.png")
    print(f"NDWI time series saved: {ndwi_csv}")

    ndmi_ts = monthly_mean_timeseries(ds_clipped, "NDMI")
    ndmi_dates = pd.to_datetime(ndmi_ts[TIME_DIM].values)
    ndmi_values = ndmi_ts.values

    ndmi_csv = config.OUTPUT_DIR / "ndmi_timeseries.csv"
    pd.DataFrame({"date": ndmi_dates, "mean_ndmi": ndmi_values}).to_csv(ndmi_csv, index=False)
    plot_ndmi_timeseries(ndmi_dates, ndmi_values, config.OUTPUT_DIR / "ndmi_timeseries.png")
    print(f"NDMI time series saved: {ndmi_csv}")

    dry_freq = dryness_frequency(ds_clipped, "NDWI", config.NDWI_DRY_THRESHOLD)
    plot_dryness_heatmap(dry_freq.values, config.OUTPUT_DIR / "dryness_heatmap.png")
    # Via download_to_path() - .rio.to_raster() hits the same Windows
    # Search Indexer/Defender file-lock race as a direct download does
    # when overwriting an existing file (see utils/downloads.py for why).
    download_to_path(lambda tmp: dry_freq.rio.to_raster(tmp), config.OUTPUT_DIR / "dryness_frequency.tif")
    print("Dryness heatmap (PNG) + GeoTIFF saved.")

    dry_magnitude = dryness_deficit_magnitude(ds_clipped, "NDWI", config.NDWI_DRY_THRESHOLD)
    download_to_path(lambda tmp: dry_magnitude.rio.to_raster(tmp), config.OUTPUT_DIR / "dryness_magnitude.tif")
    plot_water_loss_map(dry_freq.values, dry_magnitude.values, config.OUTPUT_DIR / "water_loss_map.png")
    print("Water-loss map (frequency + magnitude, PNG) + magnitude GeoTIFF saved.")

    dry_freq_ndmi = dryness_frequency(ds_clipped, "NDMI", config.NDMI_DRY_THRESHOLD)
    download_to_path(lambda tmp: dry_freq_ndmi.rio.to_raster(tmp), config.OUTPUT_DIR / "dryness_frequency_ndmi.tif")
    dry_magnitude_ndmi = dryness_deficit_magnitude(ds_clipped, "NDMI", config.NDMI_DRY_THRESHOLD)
    download_to_path(lambda tmp: dry_magnitude_ndmi.rio.to_raster(tmp), config.OUTPUT_DIR / "dryness_magnitude_ndmi.tif")
    plot_water_loss_map(
        dry_freq_ndmi.values, dry_magnitude_ndmi.values, config.OUTPUT_DIR / "water_loss_map_ndmi.png",
        title="Where the plot loses vegetation water most (NDMI-based)", index_name="NDMI",
    )
    print("Water-loss map (NDMI-based, PNG) + frequency/magnitude GeoTIFFs saved.")

    # --- ERA5 temperature context ------------------------------------------
    # bbox centre is plenty precise for ERA5 (~9-31km native resolution,
    # far coarser than the plot itself) - avoids a geopandas centroid call
    # (and its own CRS/shapely-version footguns) for no real gain in accuracy.
    lon = (bbox[0] + bbox[2]) / 2
    lat = (bbox[1] + bbox[3]) / 2
    era5_start = start.isoformat()
    era5_end = (end - relativedelta(days=1)).isoformat()  # `end` is exclusive (1st of current month)

    print("Fetching ERA5-based monthly temperature (Open-Meteo archive) ...")
    era5_temp_monthly = fetch_era5_monthly_temperature(
        lat=lat, lon=lon, start_date=era5_start, end_date=era5_end,
        cache_path=config.OUTPUT_DIR / "era5_daily_cache.csv",
    )
    era5_temp_csv = config.OUTPUT_DIR / "era5_temperature_monthly.csv"
    era5_temp_monthly.to_csv(era5_temp_csv, index=False)
    print(f"ERA5 monthly temperature saved: {era5_temp_csv}")

    print("Fetching ERA5-based monthly precipitation (Open-Meteo archive) ...")
    era5_precip_monthly = fetch_era5_monthly_precipitation(
        lat=lat, lon=lon, start_date=era5_start, end_date=era5_end,
        cache_path=config.OUTPUT_DIR / "era5_precip_daily_cache.csv",
    )
    era5_precip_csv = config.OUTPUT_DIR / "era5_precipitation_monthly.csv"
    era5_precip_monthly.to_csv(era5_precip_csv, index=False)
    print(f"ERA5 monthly precipitation saved: {era5_precip_csv}")

    def merge_and_report_correlation(index_dates, index_values, index_name, weather_df, weather_col, weather_label, out_suffix):
        """Merge one moisture index's monthly series against one ERA5
        weather series already fetched above, save the merged CSV, and
        print the Pearson correlation - same logic for NDWI/NDMI x
        temperature/precipitation, just fed a different pair each time.
        `out_suffix` picks the output filename ("temperature" keeps the
        original ndwi/ndmi_temperature_monthly.csv names other scripts
        already read; "precipitation" is the new sibling file)."""
        col = f"mean_{index_name.lower()}"
        merged_df = pd.merge(
            pd.DataFrame({"month": index_dates, col: index_values}),
            weather_df, on="month", how="inner",
        )
        merged_df.to_csv(config.OUTPUT_DIR / f"{index_name.lower()}_{out_suffix}_monthly.csv", index=False)
        if len(merged_df) >= 2:
            correlation = merged_df[col].corr(merged_df[weather_col])
            print(f"{index_name} vs. {weather_label} correlation (Pearson r, {len(merged_df)} months): {correlation:.3f}")
        else:
            print(f"Only {len(merged_df)} overlapping month(s) between {index_name} and {weather_label} data - skipping correlation.")
        return merged_df

    merged_ndwi_temp = merge_and_report_correlation(
        ndwi_dates, ndwi_values, "NDWI", era5_temp_monthly, "mean_temp_c", "temperature", "temperature",
    )
    temp_combo_png = config.OUTPUT_DIR / "ndwi_temperature_combo.png"
    plot_ndwi_temperature_combo(
        merged_ndwi_temp["month"], merged_ndwi_temp["mean_ndwi"], merged_ndwi_temp["mean_temp_c"], temp_combo_png,
    )
    print(f"NDWI/temperature combo chart saved: {temp_combo_png}")

    merged_ndwi_precip = merge_and_report_correlation(
        ndwi_dates, ndwi_values, "NDWI", era5_precip_monthly, "total_precip_mm", "precipitation", "precipitation",
    )
    precip_combo_png = config.OUTPUT_DIR / "ndwi_precipitation_combo.png"
    plot_ndwi_precipitation_combo(
        merged_ndwi_precip["month"], merged_ndwi_precip["mean_ndwi"], merged_ndwi_precip["total_precip_mm"], precip_combo_png,
    )
    print(f"NDWI/precipitation combo chart saved: {precip_combo_png}")

    # NDMI gets the same correlations + CSVs as NDWI, but not its own combo
    # charts - the two indices track each other closely enough (same
    # family, narrow- vs broad-NIR) that a second near-identical chart
    # wouldn't add much over the NDWI ones above.
    merge_and_report_correlation(ndmi_dates, ndmi_values, "NDMI", era5_temp_monthly, "mean_temp_c", "temperature", "temperature")
    merge_and_report_correlation(ndmi_dates, ndmi_values, "NDMI", era5_precip_monthly, "total_precip_mm", "precipitation", "precipitation")

    print("\nPilot run complete. Outputs in:", config.OUTPUT_DIR.resolve())


if __name__ == "__main__":
    import argparse
    import clients

    parser = argparse.ArgumentParser(description=__doc__)
    clients.add_client_arg(parser)
    args = parser.parse_args()
    clients.apply_client_overrides(config, clients.load_client(args.client))

    run_pilot()
