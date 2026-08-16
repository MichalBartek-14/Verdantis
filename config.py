"""
Central configuration for the forestry monitoring pilot.

Settings that are the SAME for every client (backend URL, collection id,
cloud-mask kernel sizes, monthly reducer, history window length, BFAST
seasonal period/penalty scale, ...) live here and don't change between
clients or runs.

Settings that DIFFER per client/plot (shapefile path, alert bbox, dryness
thresholds) live in clients/<slug>.json instead and are patched onto this
module at the top of every entry-point script's __main__ block via
clients.apply_client_overrides() - see clients.py. PLOT_SHAPEFILE /
ALERT_BBOX / OUTPUT_DIR below are therefore just fallback placeholders,
never the values an actual run uses; every entry point requires
--client <slug> and will always override them before config is read.
"""
from pathlib import Path

# --- openEO backend ---------------------------------------------------------
# Copernicus Data Space Ecosystem (CDSE) is the free openEO backend used
# here, with the full Sentinel-2 L2A archive (2015/2017-present depending
# on tile). Requires a free CDSE account (dataspace.copernicus.eu); on
# first run, connection.authenticate_oidc() will open an interactive
# device-code login (prints a URL + code if there's no browser available).
OPENEO_BACKEND_URL = "https://openeo.dataspace.copernicus.eu"
COLLECTION_ID = "SENTINEL2_L2A"

# --- Client plot ---------------------------------------------------------
# Fallback only - see the module docstring. Real value comes from
# clients/<slug>.json's "plot_shapefile" (.shp + .dbf/.shx/.prj sidecars
# must all be present in the same folder). Any CRS is fine - it's
# reprojected to EPSG:4326 automatically.
PLOT_SHAPEFILE = Path("data/PLACEHOLDER_SET_VIA_CLIENT_JSON.shp")

# Small buffer (metres) requested around the plot boundary so the raster
# grid has a pixel or two of margin before we clip back to the exact
# polygon locally - avoids edge/resampling artefacts right on the boundary.
PLOT_BUFFER_M = 20

# --- Historical pilot (NDVI time series + dryness heatmap) -------------------
HISTORY_YEARS = 5
MONTHLY_REDUCER = "median"     # median is more robust to residual cloud/shadow
                                # noise in a composite than mean
MAX_CLOUD_COVER = 80            # % scene-level cloud cover filter (CDSE's
                                 # max_cloud_cover shortcut on load_collection)

# --- Recent drought-monitoring precursor --------------------------------------
RECENT_MONTHS = 2
RECENT_PERIOD = "week"          # finer compositing interval for the
                                 # near-real-time script than the historical one

EXPORT_RECENT_GEOTIFF = False   # set True to also write full-resolution GeoTIFFs
                                 # (ndvi_<date>.tif / ndwi_<date>.tif) alongside the
                                 # PNG quicklooks in outputs/recent_composites/ -
                                 # only needed for GIS-level follow-up analysis.

# --- Spectral indices / thresholds --------------------------------------------
# NDVI = (B08 - B04) / (B08 + B04)                    -> vegetation vigour
# NDWI = (B08 - B11) / (B08 + B11)  (Gao-family index) -> canopy/soil moisture
#        proxy, broad NIR band; lower values indicate a drier signal.
# NDMI = (B8A - B11) / (B8A + B11)  (Sentinel Hub's standard NDMI)     -> same
#        family/interpretation as NDWI but narrow NIR band - highly
#        correlated with NDWI, not identical; worth comparing side by side.
#
# NDWI_DRY_THRESHOLD / NDMI_DRY_THRESHOLD below are generic pilot starting
# points, NOT calibrated operational thresholds. They should be tuned
# against field observations / local species composition before either
# feeds an alert product.
NDWI_DRY_THRESHOLD = 0.10
NDMI_DRY_THRESHOLD = 0.10

# Scene Classification (SCL) cloud/shadow/snow masking via CDSE's
# to_scl_dilation_mask process, which dilates masks around two groups of
# SCL classes (kernel1/kernel2) and then erodes small false positives.
# The values below are copied from CDSE's own example notebooks, not
# re-derived here - treat kernel sizing as a documented default rather
# than something this project validated independently.
# SCL class codes: 2 dark area, 3 cloud shadow, 4 vegetation, 5 bare soil,
# 6 water, 7 unclassified, 8/9 cloud medium/high probability, 10 thin
# cirrus, 11 snow/ice.
SCL_MASK_KWARGS = dict(
    kernel1_size=17,
    kernel2_size=77,
    mask1_values=[2, 4, 5, 6, 7],
    mask2_values=[3, 8, 9, 10, 11],
    erosion_kernel_size=3,
)

# --- Vegetation-break alert branch (BFAST-style) --------------------------------
# A separate, parallel product from the plot/sector moisture monitoring above:
# point it at ANY bounding box (not necessarily the client plot) and it pulls
# every available raw Sentinel-2 scene there (no monthly/weekly compositing),
# then flags likely structural breaks in the NDVI trend. [west, south, east,
# north] in EPSG:4326. Fallback only (see module docstring) - real value
# comes from clients/<slug>.json's "alert_bbox", which defaults to that
# client's own plot bbox so `bfast_alert.py --client <slug>` runs out of the
# box - edit the client's JSON to point it at any other area of interest.
ALERT_BBOX = [0.0, 0.0, 0.0, 0.0]
ALERT_YEARS = 5                 # how far back to pull every available scene from

# After pulling the irregular per-scene series, it's regularised onto a
# monthly grid (linear interpolation across cloud gaps) so STL decomposition
# has the fixed-frequency series it needs - this is the same irregular ->
# regular step bfast's own bfastts() does in the R package.
BFAST_SEASONAL_PERIOD = 12      # months per seasonal cycle for STL decomposition

# PELT's penalty is computed per-run, not a fixed number: penalty =
# BFAST_PENALTY_SCALE * trend.var() * log(n) - the standard BIC-style
# penalty for an L2 cost model (Killick et al. 2012). A fixed constant
# would be miscalibrated for any bbox/site whose NDVI trend has different
# variance than the one it was tuned against; scaling by the trend's own
# variance auto-adapts. Higher BFAST_PENALTY_SCALE = fewer, more
# confident breaks.
BFAST_PENALTY_SCALE = 1.0

# --- Output ----------------------------------------------------------------
# Fallback only - clients.apply_client_overrides() always repoints this at
# outputs/<slug>/ so different clients' downloads/results never collide.
OUTPUT_DIR = Path("outputs")
