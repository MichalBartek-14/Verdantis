# Verdantis

## Forestry Monitoring Pilot - Backbone

Two entry-point scripts, sharing a common `utils/` package and `config.py`:

| Script | Purpose |
|---|---|
| `pilot_historical_analysis.py` | Client-facing pilot: up to 5 years of monthly Sentinel-2 composites -> NDVI + NDWI + NDMI time series charts, a frequency+magnitude "where does the plot lose water most" map for both NDWI and NDMI, and an ERA5 temperature overlay |
| `drought_monitor_recent.py` | Last ~2 months at weekly cadence -> current NDVI/NDWI/NDMI rasters + a JSON summary, meant as the data feed a future alert product would poll |
| `build_sector_explorer_data.py` | Post-processing step (no new download - reuses `pilot_historical_analysis.py`'s output): aggregates the plot into 5x5-pixel sectors and writes `outputs/ndwi_era5_sector_explorer.html`, a clickable map (toggle NDWI/NDMI) where each sector opens its own moisture-vs-ERA5-temperature history |
| `bfast_alert.py` | A separate branch: pulls every available raw Sentinel-2 scene (no compositing) over a user-set `ALERT_BBOX` (any area, not just the client plot), plots the raw NDVI series, and flags likely structural breaks (harvest, dieback, land-use change) with a BFAST-style trend decomposition + changepoint search |

```
forestry_pilot/
├── config.py                      # all client/site-specific settings live here
├── pilot_historical_analysis.py   # entry point 1
├── drought_monitor_recent.py      # entry point 2
├── build_sector_explorer_data.py  # entry point 3 (run after entry point 1)
├── bfast_alert.py                 # entry point 4 (independent - own bbox, own download)
├── requirements.txt
├── data/                          # put the client's shapefile here
└── utils/
    ├── plot_geometry.py           # shapefile loading, bbox/buffer
    ├── openeo_client.py           # connection + OIDC auth
    ├── cloud_masking.py           # SCL-based cloud/shadow/snow mask
    ├── indices.py                 # NDVI/NDWI/NDMI band math
    ├── raster_analysis.py         # local xarray clip/timeseries/frequency/magnitude stats
    ├── plotting.py                # matplotlib chart + heatmap generation
    ├── weather.py                 # ERA5 temperature via Open-Meteo's archive API (no key needed)
    └── downloads.py               # download-to-temp-then-move (works around a Windows file-lock issue)
```

`bfast_alert.py` is intentionally separate from the sector explorer above (a genuinely
interactive "draw a bbox on a satellite basemap" picker can't run inside a published
Claude Artifact - the CSP blocks all external tile/CDN requests - so the bbox is instead
set once in `config.py`).

## Setup

```bash
pip install -r requirements.txt
```

You need a free [Copernicus Data Space Ecosystem](https://dataspace.copernicus.eu/) account.
On first run, `authenticate_oidc()` opens an interactive device-code login
(browser popup, or a URL+code printed to the console if headless). The
openEO client caches the token locally afterwards.

Drop the client's shapefile (`.shp` + `.dbf`/`.shx`/`.prj`) into `data/`
and point `PLOT_SHAPEFILE` in `config.py` at it.

## Run

```bash
python pilot_historical_analysis.py   # multi-year pilot deliverable
python drought_monitor_recent.py      # recent-conditions snapshot
python build_sector_explorer_data.py  # run after the historical pilot - builds the sector explorer
python bfast_alert.py                 # independent - set ALERT_BBOX in config.py first
```

Outputs land in `outputs/`:

- `ndvi_timeseries.png` / `.csv` - plot-average NDVI per month
- `ndwi_timeseries.png` / `.csv`, `ndmi_timeseries.png` / `.csv` - plot-average NDWI
  and NDMI per month
- `dryness_heatmap.png` / `dryness_frequency.tif` - % of months each pixel
  was classified "dry" (NDWI below threshold)
- `water_loss_map.png` / `dryness_magnitude.tif` - companion map to the above: for
  each pixel, the average NDWI deficit *when* it was dry (severity, not just frequency)
- `water_loss_map_ndmi.png` / `dryness_frequency_ndmi.tif` / `dryness_magnitude_ndmi.tif` -
  the same frequency+magnitude map, NDMI-based instead of NDWI-based
- `era5_temperature_monthly.csv` - ERA5-based monthly mean air temperature for the
  plot (via Open-Meteo's archive API, no account/key needed)
- `ndwi_temperature_monthly.csv` / `ndwi_temperature_combo.png` - the NDWI series merged
  against ERA5 temperature, plus a printed Pearson correlation, to sanity-check whether
  moisture drops track warm spells
- `ndmi_temperature_monthly.csv` - the same merge for NDMI (correlation printed, no
  separate combo chart - NDWI and NDMI track each other closely enough that a second
  near-identical chart wouldn't add much)
- `sector_explorer_data.json` / `ndwi_era5_sector_explorer.html` - interactive version of
  the above: the plot split into 5x5-pixel sectors (partial at the edges), toggle NDWI/NDMI
  and dry frequency/dry magnitude, click any sector for its own moisture + ERA5 temperature
  history and stats. Self-contained HTML - open it directly in a browser, no server needed.
- `ndvi_latest_<date>.tif`, `ndwi_latest_<date>.tif`, `ndmi_latest_<date>.tif`,
  `drought_summary_<date>.json` from the recent-monitoring script - the "current
  conditions" machine-readable feed
- `recent_composites/ndvi_quicklook_<date>.png`, `ndwi_quicklook_<date>.png`,
  `ndmi_quicklook_<date>.png` - one triple per weekly composite over the RECENT_MONTHS
  window, for browsing how conditions changed week to week (set
  `EXPORT_RECENT_GEOTIFF = True` in config.py to also get matching `.tif` files for GIS use)
- `alert_ndvi_raw.csv` - every usable raw Sentinel-2 scene's NDVI over `ALERT_BBOX`
  (irregular dates, no compositing)
- `alert_breaks.json` / `alert_ndvi_breaks.png` - detected structural breaks (date,
  trend before/after, magnitude) and the chart showing the raw scatter, fitted trend,
  and each break as a vertical line - from `bfast_alert.py`

## Key assumptions this pilot makes (check before showing to a client)

- **Backend**: Copernicus Data Space Ecosystem's openEO endpoint,
  collection `SENTINEL2_L2A`.
- **Cloud masking**: CDSE's `to_scl_dilation_mask` process on the SCL
  band, using the kernel sizes from CDSE's own example notebooks - not
  independently tuned for this project.
- **Dryness definition**: NDWI = (B08-B11)/(B08+B11) (broad NIR), flagged "dry"
  below `NDWI_DRY_THRESHOLD` (default 0.10). NDMI = (B8A-B11)/(B8A+B11) (narrow
  NIR - Sentinel Hub's standard NDMI definition) uses the same threshold
  convention via `NDMI_DRY_THRESHOLD`. Same family, highly correlated, not
  identical - both are generic pilot starting points, not calibrated
  operational thresholds - they should be checked against field observations
  and the client's species/soil conditions before being used to drive real alerts.
- **Compositing**: monthly median composites for the historical pilot,
  weekly for the recent script. Sparse cloud-free coverage in a given
  month/week will leave gaps (NaN) rather than an interpolated value -
  the current scripts don't gap-fill.
- **Geometry**: imagery is requested for the plot's bounding box (plus a
  small buffer) and clipped to the exact polygon locally after download,
  so pixels outside the plot are excluded from all statistics.
- **ERA5 temperature source**: pulled from Open-Meteo's free, keyless historical
  archive API (ERA5/ERA5-Land reanalysis) rather than the raw Copernicus Climate
  Data Store (`cdsapi`), which needs its own separate account + API key. Swap in
  `cdsapi` in `utils/weather.py` if you need other ERA5 variables or the full CDS
  dataset. Uses the plot's bounding-box centre as the query point - fine given
  ERA5's ~9-31km native resolution is far coarser than the plot itself.
- **GeoTIFF writes go through `download_to_path()` too**, not just openEO downloads -
  `.rio.to_raster()` deletes-then-recreates an existing destination file in place,
  which hits the same Windows Search Indexer/Defender file-lock race as a direct
  network download does when overwriting a file that already exists. If a run ever
  fails with `PermissionError: ... Access is denied` on a `.tif` that already existed
  from a previous run, that's this - retry, or reboot if it persists (Windows can hold
  the lock indefinitely on some machines).
- **`pilot_historical_analysis.py` and `bfast_alert.py` skip re-downloading** if their
  main `.nc` output already exists in `outputs/` - delete it to force a fresh pull
  (e.g. once new months/scenes are available). `drought_monitor_recent.py` and
  `build_sector_explorer_data.py` don't cache this way since they're meant to reflect
  the *latest* available data on every run.
- **`bfast_alert.py`'s break detection is BFAST-*style*, not literally BFAST**: the
  real `bfast` Python package hard-requires `pyopencl`/a working OpenCL runtime (it's
  built for GPU-accelerated per-pixel processing of large rasters), and the reference
  implementation is an R package - neither is practical to depend on for this pilot.
  `bfast_alert.py` instead uses statsmodels' STL to decompose the (monthly-regularised)
  NDVI series into trend + season + remainder, then ruptures' PELT to find changepoints
  in the trend - the same conceptual approach BFAST (Verbesselt et al.) is built on,
  via mature, GPU-free, pip-installable libraries. Treat detected breaks as candidates
  to investigate, not calibrated alerts.

## Natural next steps (beyond this pilot)

- Calibrate `NDWI_DRY_THRESHOLD` (and consider whether this NDWI
  formulation is the right moisture proxy for the client's species vs.
  a species-specific index) against ground truth.
- Turn `drought_monitor_recent.py` into a scheduled job (cron / Airflow)
  that persists each run's summary and diffs against the previous one to
  generate actual alerts, rather than a one-off snapshot.
- Add gap-filling/interpolation for months or weeks with no cloud-free
  observations if the client wants a continuous series rather than NaNs.
- Multi-plot support (currently one shapefile = one plot per run).
