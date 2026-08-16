# Verdantis

## Forestry Monitoring Pilot - Backbone

Four entry-point scripts, sharing a common `utils/` package and `config.py`, plus a
static, multi-client site (`docs/`) published from their output:

| Script | Purpose |
|---|---|
| `pilot_historical_analysis.py` | Client-facing pilot: up to 5 years of monthly Sentinel-2 composites -> NDVI + NDWI + NDMI time series charts, a frequency+magnitude "where does the plot lose water most" map for both NDWI and NDMI, and an ERA5 temperature overlay |
| `drought_monitor_recent.py` | Last ~2 months at weekly cadence -> current NDVI/NDWI/NDMI rasters + a JSON summary, meant as the data feed a future alert product would poll |
| `build_sector_explorer_data.py` | Post-processing step (no new download - reuses `pilot_historical_analysis.py`'s output): aggregates the plot into 5x5-pixel sectors and writes `outputs/<client>/sector_explorer_data.json` for the site's interactive Sector Explorer page (toggle NDWI/NDMI, click a sector for its own moisture-vs-ERA5-temperature history), plus a year of monthly NDVI/NDWI/NDMI quicklooks for the site's Monitoring page |
| `bfast_alert.py` | A separate branch: pulls every available raw Sentinel-2 scene (no compositing) over a client's `alert_bbox` (any area, not just the plot itself), plots the raw NDVI series, and flags likely structural breaks (harvest, dieback, land-use change) with a BFAST-style trend decomposition + changepoint search - over both the full history and a "last year" zoom into the same fit |
| `render_true_color.py` | Independent of the other four - turns a true-color satellite GeoTIFF (produced outside this pipeline, dropped into `data/<client>/` next to the shapefile) into the PNG shown on the title page hero, next to the title. Safe to run before that GeoTIFF exists - see **Title page photo** below |

Every script takes a required `--client <slug>` argument - see **Multiple clients** below.

```
forestry_pilot/
├── config.py                      # settings shared by every client (backend, cloud mask, ...)
├── clients.py                     # per-client registry loader + config-override wiring
├── clients/
│   ├── valice.json                # one JSON per client - shapefile, bbox, thresholds, branding
│   └── _example.json.template     # schema reference for onboarding a new client
├── pilot_historical_analysis.py   # entry point 1
├── drought_monitor_recent.py      # entry point 2
├── build_sector_explorer_data.py  # entry point 3 (run after entry point 1)
├── bfast_alert.py                 # entry point 4 (independent - own bbox, own download)
├── render_true_color.py           # entry point 5 (independent - GeoTIFF -> hero photo PNG)
├── publish_site.py                # outputs/<client>/ -> docs/c/<client>/ (the only backend<->site link)
├── check_translations.py          # fails if any docs/_template i18n key is missing for any language
├── requirements.txt
├── data/<client>/                 # each client's shapefile lives in its own subfolder (gitignored)
├── outputs/<client>/              # each client's downloaded rasters + generated charts (gitignored)
├── docs/                          # the published static site (see "The site" below)
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
set once per client in `clients/<slug>.json`).

## Setup

```bash
pip install -r requirements.txt
```

You need a free [Copernicus Data Space Ecosystem](https://dataspace.copernicus.eu/) account.
On first run, `authenticate_oidc()` opens an interactive device-code login
(browser popup, or a URL+code printed to the console if headless). The
openEO client caches the token locally afterwards - shared across every
client, since it's one machine/account, not one login per client.

## Multiple clients

Everything that varies plot-to-plot lives in `clients/<slug>.json`, not in code -
see `clients/valice.json` for a real one and `clients/_example.json.template` for
the schema. To onboard a new client:

1. Drop their shapefile (`.shp` + `.dbf`/`.shx`/`.prj`) into `data/<slug>/`.
2. Copy `clients/_example.json.template` to `clients/<slug>.json` and fill it in
   (shapefile path, `alert_bbox`, display name/location for the site, optional
   per-client NDWI/NDMI threshold overrides, optional accent color, and `language` -
   see **Language** under "The site" below for what's available).
3. Run the pipeline and publish - see **Run** and **The site** below.

`config.py` still holds everything that's the *same* for every client (backend URL,
cloud-mask kernel sizes, monthly reducer, BFAST seasonal period, ...); `clients.py`
patches only the per-client attributes onto it at the start of each script's
`__main__`, and namespaces `OUTPUT_DIR` under `outputs/<slug>/` so clients' runs
never collide.

## Run

```bash
python pilot_historical_analysis.py --client valice   # multi-year pilot deliverable
python drought_monitor_recent.py --client valice       # recent-conditions snapshot
python build_sector_explorer_data.py --client valice   # run after the historical pilot
python bfast_alert.py --client valice                  # independent - alert_bbox from clients/valice.json
```

Outputs land in `outputs/<client>/`:

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
- `sector_explorer_data.json` - the plot split into 5x5-pixel sectors (partial at the
  edges), dry frequency/dry magnitude for both NDWI and NDMI, full-history and
  last-year windows, plus a year of whole-plot NDVI/NDWI/NDMI quicklook images -
  everything the site's Sector Explorer and Monitoring pages need. Not meant to be
  opened directly; `publish_site.py` splits it into `docs/c/<client>/data/`.
- `ndvi_latest_<date>.tif`, `ndwi_latest_<date>.tif`, `ndmi_latest_<date>.tif`,
  `drought_summary_<date>.json` from the recent-monitoring script - the "current
  conditions" machine-readable feed
- `recent_composites/ndvi_quicklook_<date>.png`, `ndwi_quicklook_<date>.png`,
  `ndmi_quicklook_<date>.png` - one triple per weekly composite over the RECENT_MONTHS
  window, for browsing how conditions changed week to week (set
  `EXPORT_RECENT_GEOTIFF = True` in config.py to also get matching `.tif` files for GIS use)
- `alert_ndvi_raw.csv` - every usable raw Sentinel-2 scene's NDVI over the client's
  `alert_bbox` (irregular dates, no compositing)
- `alert_breaks.json` / `alert_ndvi_breaks.png` / `alert_ndvi_breaks_1y.png` - detected
  structural breaks (date, trend before/after, magnitude), nested under both a full-history
  and a "last year" window (same STL/PELT fit, windowed for display - see `bfast_alert.py`'s
  `window_view()`), and the matching chart for each window - from `bfast_alert.py`

## The site

`docs/` is a static site, deployed as-is (GitHub Pages, Netlify, ...) with **no backend** -
the browser never talks to this machine or to openEO. It has three parts:

- `docs/index.html` - a client picker, reading `docs/clients.json` (a manifest of every
  published client's slug/name/location).
- `docs/_template/` - the ONE hand-maintained site template (4 pages: Overview, Historical
  Pilot, Sector Explorer, Monitoring & Alerts), byte-identical across every client. Personalizes
  itself at runtime from `data/client_meta.json` (name, location, plot area, accent color,
  language) via `assets/client.js` - see there for exactly what it touches. Edit pages here;
  never edit inside `docs/c/<slug>/` directly, since the next publish overwrites it.
- `docs/c/<slug>/` - one folder per published client, generated by `publish_site.py`:
  the template copied verbatim, plus that client's own `assets/img/` and `data/*.json`.

### Language

Every client picks a `language` in their `clients/<slug>.json` (currently `en` or `sk` -
Valice is `sk`, since the plot's own client speaks Slovak). The site template's copy is
never hardcoded in one language: visible text is marked `data-i18n="some.key"` (or
`data-i18n-html="..."` where it needs embedded markup) instead of literal English, and
`assets/client.js` fetches `assets/i18n/<language>/<page>.json` + `common.json` at page
load and fills every `[data-i18n]` element in - the same mechanism that already
personalizes client name/location, just keyed by language instead of by client. Text a
page builds itself in JS (table rows, chart labels, tooltips, month names, ...) calls the
same `t(key, vars)` function, exposed once translations are loaded via
`window.VerdantisReady`.

**Adding new site content**: wrap it in `data-i18n`/`data-i18n-html` and add the key to
*every* language's JSON for that page (`docs/_template/assets/i18n/en/<page>.json`,
`.../sk/<page>.json`, ...) - then run:

```bash
python check_translations.py
```

which fails loudly (non-zero exit, listing exactly what's missing) if any key exists in
one language's dictionary but not another's, for any page. This is what actually keeps
future additions in sync across languages - not just a convention to remember.

**Adding a new language**: add a `docs/_template/assets/i18n/<code>/` folder with a
`common.json` + one `<page>.json` per existing page (copy an existing language's as a
starting point), run `check_translations.py` to confirm nothing's missing, then set
`"language": "<code>"` in any client's JSON. `publish_site.py` refuses to publish a
client whose configured language has no matching dictionary folder.

### Title page photo

The Overview page's hero reserves a frame next to the title for a true-color satellite
photo of the plot (`docs/_template/index.html`'s `.hero-image`, see
`docs/_template/assets/style.css` for its CSS). That frame always exists, even for a
client with no photo yet - it just shows a dashed placeholder ("coming soon") until one
is published, so nothing shifts or looks broken either way.

The source GeoTIFF is produced by a separate process outside this pipeline (not by any
script here), and is expected to already be cropped/composited to the client's plot in
the **same CRS as that client's shapefile**. Workflow once it exists:

1. Drop it into `data/<client>/` (the same folder as the shapefile) - any filename, as
   long as it's the only `.tif`/`.tiff` there. `render_true_color.py` auto-discovers it;
   set `"true_color_tif"` in `clients/<slug>.json` only if that folder ever holds more
   than one GeoTIFF and auto-discovery would be ambiguous.
2. `python render_true_color.py --client <slug>` (or `--all`) - percentile-stretches
   each band for a natural-looking quicklook (works regardless of the source's dtype/
   scale - 0-1 float, 0-10000 Sentinel-2 DN, already-uint8, ...) and caps the long edge
   at 1600px so the hero photo stays a light web asset regardless of the source
   resolution. Safe to run before the GeoTIFF exists - it reports that and exits 0.
3. `python publish_site.py --client <slug>` picks up `outputs/<client>/true_color.png`
   if `render_true_color.py` produced one.

No reprojection or polygon clipping happens here - the script assumes the source is
already prepared for direct display. Re-run `render_true_color.py` any time the source
GeoTIFF is replaced with a newer one.

Publish (after running the pipeline for a client):

```bash
python publish_site.py --client valice   # one client
python publish_site.py --all             # every client in clients/
```

then review `docs/` locally and `git add docs/` + commit + push.

**Data isolation / access control**: this repository is one shared codebase for every
client, but `docs/c/<slug>/` folders are meant to be deployed - and gated - independently.
Static hosting has no per-file ACL: anyone with a `docs/c/<slug>/...` URL can read that
client's data, full stop. For a real multi-client rollout, put each client's path (or
subdomain) behind an access-control layer at the hosting/edge level - e.g. one
[Cloudflare Access](https://developers.cloudflare.com/cloudflare-one/policies/access/)
policy per `/c/<slug>/*` path or per client subdomain, restricted to that client's email
domain. That's a hosting/DNS decision, not something this codebase can enforce itself.

## Key assumptions this pilot makes (check before showing to a client)

- **Backend**: Copernicus Data Space Ecosystem's openEO endpoint,
  collection `SENTINEL2_L2A`.
- **Cloud masking**: CDSE's `to_scl_dilation_mask` process on the SCL
  band, using the kernel sizes from CDSE's own example notebooks - not
  independently tuned for this project.
- **Dryness definition**: NDWI = (B08-B11)/(B08+B11) (broad NIR), flagged "dry"
  below `NDWI_DRY_THRESHOLD` (default 0.10, overridable per client). NDMI =
  (B8A-B11)/(B8A+B11) (narrow NIR - Sentinel Hub's standard NDMI definition) uses
  the same threshold convention via `NDMI_DRY_THRESHOLD`. Same family, highly
  correlated, not identical - both are generic pilot starting points, not
  calibrated operational thresholds - they should be checked against field
  observations and each client's species/soil conditions before being used to
  drive real alerts.
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
  main `.nc` output already exists in `outputs/<client>/` - delete it to force a fresh
  pull (e.g. once new months/scenes are available). `drought_monitor_recent.py` and
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
- **The "last year" alert window is a display filter, not a shorter model**: STL with a
  12-month seasonal period needs >=24 months of data to decompose meaningfully, so
  `bfast_alert.py` always fits on the full history and windows the chart/table for the
  "last year" view - see `window_view()` there.

## Natural next steps (beyond this pilot)

- Calibrate `NDWI_DRY_THRESHOLD`/`NDMI_DRY_THRESHOLD` per client (and consider
  whether this NDWI formulation is the right moisture proxy for each client's
  species vs. a species-specific index) against ground truth.
- Turn `drought_monitor_recent.py` into a scheduled job (cron / Airflow, looped
  over every client) that persists each run's summary and diffs against the
  previous one to generate actual alerts, rather than a one-off snapshot.
- Add gap-filling/interpolation for months or weeks with no cloud-free
  observations if a client wants a continuous series rather than NaNs.
- Multi-plot-per-client support (currently one shapefile = one plot per client).
- Real access control per client site (see "Data isolation / access control" above) -
  currently a deploy-time decision this repo documents but doesn't enforce.
