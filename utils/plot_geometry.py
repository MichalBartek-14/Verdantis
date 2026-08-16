"""
Helpers for loading the client's plot shapefile and deriving the spatial
extents needed for the openEO requests.
"""
from pathlib import Path
import geopandas as gpd


def load_plot(shapefile_path: Path) -> gpd.GeoDataFrame:
    """Load the client's plot shapefile and reproject to EPSG:4326
    (lat/lon), which is what openEO's spatial_extent expects."""
    shapefile_path = Path(shapefile_path)
    if not shapefile_path.exists():
        raise FileNotFoundError(
            f"Plot shapefile not found: {shapefile_path}. "
            "Update PLOT_SHAPEFILE in config.py to point at the client's data "
            "(make sure the .dbf/.shx/.prj sidecar files are alongside the .shp)."
        )

    gdf = gpd.read_file(shapefile_path)
    if gdf.empty:
        raise ValueError(f"Shapefile {shapefile_path} contains no features.")

    if gdf.crs is None:
        raise ValueError(
            f"{shapefile_path} has no CRS defined - fix the .prj file before proceeding."
        )

    return gdf.to_crs(epsg=4326)


def get_bbox(gdf: gpd.GeoDataFrame, buffer_m: float = 0) -> list:
    """Return [west, south, east, north] in EPSG:4326 for openEO's
    spatial_extent, optionally buffered by `buffer_m` metres."""
    if buffer_m:
        # Buffering by metres needs a projected (metric) CRS - use the
        # plot's local UTM zone, then reproject the buffered shape back.
        utm_crs = gdf.estimate_utm_crs()
        buffered = gdf.to_crs(utm_crs).buffer(buffer_m).to_crs(epsg=4326)
        bounds = buffered.total_bounds
    else:
        bounds = gdf.total_bounds

    west, south, east, north = bounds
    return [west, south, east, north]
