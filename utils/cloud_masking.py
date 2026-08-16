"""
Cloud/shadow/snow masking, shared by the historical pilot and the recent
drought-monitoring script so both products are cloud-filtered identically.

Uses CDSE's `to_scl_dilation_mask` process on the Sentinel-2 Scene
Classification (SCL) band - this is the pattern documented in CDSE's own
openEO example notebooks, rather than a hand-rolled per-class mask.
"""
import config


def build_cloud_mask(connection, bbox, temporal_extent):
    """Load just the SCL band for the given extent and turn it into a
    boolean mask cube (True = pixel should be masked out)."""
    scl = connection.load_collection(
        config.COLLECTION_ID,
        spatial_extent={
            "west": bbox[0], "south": bbox[1], "east": bbox[2], "north": bbox[3],
            "crs": "EPSG:4326",
        },
        temporal_extent=temporal_extent,
        bands=["SCL"],
        max_cloud_cover=config.MAX_CLOUD_COVER,
    )
    cloud_mask = scl.process("to_scl_dilation_mask", data=scl, **config.SCL_MASK_KWARGS)
    return cloud_mask


def apply_cloud_mask(data_cube, cloud_mask):
    """Resample the (20 m) SCL-derived mask onto the data cube's own grid
    and apply it, nulling out masked pixels."""
    cloud_mask = cloud_mask.resample_cube_spatial(data_cube)
    return data_cube.mask(cloud_mask)
