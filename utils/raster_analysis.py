"""
Local (post-download) raster analysis helpers, operating on the NetCDF
cubes produced by the openEO pipeline scripts. Kept separate from the
openEO calls so this logic can be reused/tested without a live backend
connection.
"""
import numpy as np
import xarray as xr
import geopandas as gpd
import rioxarray  # noqa: F401  (registers the .rio accessor on xarray objects)

TIME_DIM = "t"  # openEO NetCDF exports name the temporal dimension "t"


def open_cube(netcdf_path) -> xr.Dataset:
    """Open a downloaded NetCDF cube and make sure it carries a usable
    CRS + a consistently-named time dimension.

    Despite spatial_extent being requested in EPSG:4326, CDSE's openEO
    backend returns the pixel grid in the tile's native UTM zone (x/y in
    metres) and records the real CRS as a CF grid_mapping variable - it
    does NOT reproject to EPSG:4326 server-side. decode_coords="all"
    makes xarray/rioxarray parse that grid_mapping automatically so
    ds.rio.crs reflects the actual (UTM) CRS instead of coming back None
    (which previously caused clip_to_geometry() to silently produce an
    all-NaN result, since the plot polygon in real degrees never
    overlapped a grid mislabelled as degrees but actually in metres)."""
    ds = xr.open_dataset(netcdf_path, decode_coords="all")

    if "time" in ds.dims and TIME_DIM not in ds.dims:
        ds = ds.rename({"time": TIME_DIM})

    if ds.rio.crs is None:
        # Fallback only - real CDSE responses carry their own grid_mapping
        # (see above) so this shouldn't normally trigger.
        ds = ds.rio.write_crs("EPSG:4326")

    return ds


def clip_to_geometry(ds: xr.Dataset, gdf: gpd.GeoDataFrame) -> xr.Dataset:
    """Clip the downloaded bbox raster to the client's exact plot
    polygon(s), setting pixels outside the polygon to NaN rather than
    dropping them from the grid (drop=False keeps array shape stable)."""
    gdf_matched = gdf.to_crs(ds.rio.crs)
    return ds.rio.clip(gdf_matched.geometry.values, gdf_matched.crs, drop=False, all_touched=False)


def monthly_mean_timeseries(ds: xr.Dataset, variable: str) -> xr.DataArray:
    """Plot-wide spatial mean of `variable` for every time step."""
    return ds[variable].mean(dim=("x", "y"), skipna=True)


def dryness_frequency(ds: xr.Dataset, variable: str, threshold: float) -> xr.DataArray:
    """For every pixel, the % of time steps where `variable` fell below
    `threshold` (i.e. how often that pixel looked 'dry'). Time steps
    masked out by cloud (NaN) are excluded from both the numerator and
    denominator per pixel, so cloud gaps don't bias the frequency."""
    valid = ds[variable].notnull()
    dry = (ds[variable] < threshold) & valid

    n_valid = valid.sum(dim=TIME_DIM)
    n_dry = dry.sum(dim=TIME_DIM)

    frequency = xr.where(n_valid > 0, n_dry / n_valid, np.nan) * 100.0
    frequency.name = f"{variable}_dry_frequency_pct"
    return frequency


def dryness_deficit_magnitude(ds: xr.Dataset, variable: str, threshold: float) -> xr.DataArray:
    """For every pixel, the average magnitude of `variable` falling below
    `threshold` on the time steps where it did (mean(threshold - value)
    over 'dry' steps only) - i.e. how much moisture was typically lost
    on the occasions this pixel did run dry, complementing
    dryness_frequency()'s "how often". Pixels that are valid but were
    never dry get 0; pixels with no valid data at all get NaN."""
    valid = ds[variable].notnull()
    dry = (ds[variable] < threshold) & valid
    deficit = xr.where(dry, threshold - ds[variable], 0.0)

    n_valid = valid.sum(dim=TIME_DIM)
    n_dry = dry.sum(dim=TIME_DIM)
    sum_deficit = deficit.sum(dim=TIME_DIM)

    magnitude = xr.where(n_valid > 0, xr.where(n_dry > 0, sum_deficit / n_dry, 0.0), np.nan)
    magnitude.name = f"{variable}_dry_deficit_magnitude"
    return magnitude
