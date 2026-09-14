# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Verdantis: a Sentinel-2-based pilot for monitoring forestry/agriculture/greenery plot
moisture, vegetation vigour, and structural vegetation breaks - free Copernicus imagery
in, a published static multi-client dashboard site out. Two halves:

1. **Backend** (repo root, Python): five independent entry-point scripts pull/process
   Sentinel-2 + ERA5 data per client and write to `outputs/<slug>/`. No server, no
   database - each script is a one-shot batch job run by hand.
2. **Site** (`docs/`): a static, no-backend multi-client dashboard, hand-built from
   `outputs/<slug>/` by `publish_site.py`, deployed as-is (Netlify today).

Nothing here runs automatically - there is no CI/cron pulling new imagery. Refreshing a
client's dashboard is always: run the relevant script(s) -> `publish_site.py` -> commit
`docs/` -> push.

## Commands

Setup:
```bash
pip install -r requirements.txt
```
There's no test suite. The closest thing to a check is:
```bash
python check_translations.py       # fails loudly if any i18n key is missing in any language
```
run this after touching anything under `docs/_template/assets/i18n/`.

Every pipeline script takes a required `--client <slug>` (or `--all` for
`publish_site.py`/`render_true_color.py`/`ingest_sensor_data.py`):
```bash
python pilot_historical_analysis.py --client <slug>    # multi-year pilot deliverable
python drought_monitor_recent.py --client <slug>       # recent-conditions snapshot
python build_sector_explorer_data.py --client <slug>   # run AFTER pilot_historical_analysis.py
python bfast_alert.py --client <slug>                  # independent - own bbox, own download
python render_true_color.py --client <slug>            # independent - GeoTIFF -> hero photo PNG
python ingest_sensor_data.py --client <slug>            # independent - sensor_uploads/<slug>/ -> outputs/<slug>/
python publish_site.py --client <slug>                 # outputs/<slug>/ -> docs/c/<slug>/
```
First run of any script that talks to openEO opens an interactive OIDC device-code login
(browser popup, or a URL+code printed to the console if headless); the token is then
cached locally and shared across every client, so this is normally a one-time prompt per
machine, not per client.

## Architecture

**Config split**: `config.py` holds everything identical across every client (backend
URL, cloud-mask kernel sizes, monthly reducer, BFAST params, ...). Everything that
varies per plot (shapefile path, `alert_bbox`, threshold overrides, display metadata,
i18n tweaks) lives in one `clients/<slug>.json` per client (schema documented inline in
`clients/_example.json.template`). `clients.py`'s `apply_client_overrides()` patches the
per-client fields onto the imported `config` module at the start of every script's
`__main__` - `utils/*.py`, which reads straight from `config`, never needs to know a
multi-client registry exists. `clients.py` also namespaces `config.OUTPUT_DIR` under
`outputs/<slug>/` so two clients' runs never collide.

**Onboarding a new client**: drop the shapefile (`.shp`+`.dbf`/`.shx`/`.prj`) into
`data/<slug>/`, copy `clients/_example.json.template` to `clients/<slug>.json` and fill
it in (shapefile path, `alert_bbox`, display name/location, language, accent color;
`plot_area_ha`/`alert_bbox` can be computed from the shapefile itself with geopandas
rather than guessed), run the pipeline scripts, then `publish_site.py`. Also add the new
client's Basic Auth row to `netlify/edge-functions/protect-clients.js` (see below) - it
does NOT happen automatically, and the function fails *open* (public, unprotected) for
any `/c/<slug>/` prefix that isn't in its `PROTECTED` list, so a forgotten row is a real
exposure, not just a cosmetic gap.

**The bfast_alert branch is intentionally separate**: `pilot_historical_analysis.py` /
`drought_monitor_recent.py` / `build_sector_explorer_data.py` all work over the client's
*plot* (monthly/weekly composites, clipped to the shapefile). `bfast_alert.py` instead
pulls every raw Sentinel-2 scene (no compositing) over the client's `alert_bbox`, which
can be any area of interest - it defaults to the plot's own bbox but doesn't have to be.

**Site personalization/i18n**: `docs/_template/` is ONE hand-maintained template (4
pages: Overview, Historical Pilot, Sector Explorer, Monitoring & Alerts), copied
byte-identical into `docs/c/<slug>/` by `publish_site.py` on every publish - **never
edit inside `docs/c/<slug>/` directly**, the next publish silently overwrites it. The
template personalizes itself at runtime purely from `data/client_meta.json` (written by
`publish_site.py`) via `assets/client.js`: elements opt in with `data-client-*`
attributes (name/location/area/accent color) and `data-i18n`/`data-i18n-html` (text,
resolved from `assets/i18n/<language>/<page>.json` + `common.json`, fetched at page
load). Adding any new visible text means adding the key to *every* language's JSON for
that page and running `check_translations.py` - it's what actually enforces parity, not
just a convention. `clients/<slug>.json`'s optional `i18n_overrides` lets one client's
JSON patch template wording without touching the shared template (e.g. "forestry plot"
-> "urban green infrastructure" for a client that isn't a forest).

**The plot-location map** (`docs/_template/index.html`) prefers `true_color_bounds.json`
(precise photo bounds, written by `render_true_color.py`) but falls back to
`client_meta.json`'s `plot_bounds` (plain bbox, always present) so the map itself is
never gated on the separate true-color-photo pipeline having run yet.

**The 3-page intro briefing** (`docs/index.html` + `intro-2.html` + `intro-3.html`,
Slovak translation under `docs/sk/`) is deliberately outside `_template/` - hand-written,
no per-client data, no i18n system, one copy per language kept structurally in sync by
hand. It's what a visitor sees before picking a client on `plots.html`.

**Data isolation is a hosting concern, not a code one**: every client's `docs/c/<slug>/`
is meant to be access-controlled independently in production (Netlify Edge Function
Basic Auth today - see `netlify/edge-functions/protect-clients.js`), but nothing in this
repo enforces that locally. This is also why brand assets aren't shared across trees -
see below.

**Brand logo**: `docs/_template/assets/brand-logo.js` (`initBrandLogo(prefix)`) swaps the
CSS gradient-box + "Verdantis" text lockup for a real `<prefix>logo-full.png` once one
exists - safe to call before it does, same probe-then-swap pattern as the intro
briefing's photo slots. The script itself is loaded cross-tree by the standalone
briefing pages (same as `_template/assets/style.css` already is), but the actual image
files are NOT - each of `docs/assets/img/brand/` (briefing pages) and
`docs/_template/assets/img/brand/` (dashboard template, copied per-client on publish)
keeps its own copy of `logo-full.png`/`logo-small.png`, so a published `docs/c/<slug>/`
stays self-contained per the isolation note above. `logo-small.png` also doubles as the
favicon/apple-touch-icon everywhere. See the `PUT_LOGO_FILES_HERE.txt` in both folders.

**Live sensor data**: a client can have `"live_sensor_feed": true` in
`clients/<slug>.json` (Devinska today) to show live field-sensor data on the same
plot-location map. TWO independent feeds, not one combined reading -
`outputs/<slug>/sensor_track.json` (position tracker, `{time, lat, lon}[]`, no
temperature) and `sensor_temperature.json` (stationary sensor, `{time, temperature_c,
soil_moisture?}[]`, no position - its fixed spot is `clients/<slug>.json`'s own
`sensor_location`, falling back to the plot's center if unset). `publish_site.py` copies
whichever exist into `docs/c/<slug>/data/`; `docs/_template/index.html`'s map script
renders each independently and skips cleanly if absent (it only reads `time`/
`temperature_c` from the temperature feed today - `soil_moisture` is published but not
yet surfaced on the map). `ingest_sensor_data.py --client <slug>` (or `--all`) produces
`sensor_temperature.json` from TWO merged sources: it polls the live field-sensor API
itself (`config.SENSOR_API_BASE_URL` + `/api/v1/temperature` - a separately-run FastAPI
service documented in `data/verdantis-sensor-infra-reference.md`, not built by this
repo; auth key resolved per `secrets/README.md`, incrementally via the API's own
`after_id` "what's new since I last checked" parameter once local history exists), and
it parses whatever's sitting in `sensor_uploads/<slug>/temperature/` (a git-tracked drop
zone, unlike gitignored `data/`, for anything dropped in by hand). Every live pull is
itself saved as a new timestamped file into that same drop zone, so a live reading and a
hand-dropped export are ingested identically and every pull stays in the audit trail.
`--no-fetch` skips the live poll and parses local drops only. Deliberately ONE small
deterministic parser written against a real sample (see `sensor_uploads/devinska/README.md`
for the exact format(s)), not an LLM-in-the-loop "figure out the format every run" step.
`track/` isn't ingested yet - no real export has been seen for that sensor, so its
format (and therefore `sensor_track.json`) is still unwritten; extend
`ingest_sensor_data.py` with a second parser once one shows up, rather than assuming it
matches the temperature sensor's format.
