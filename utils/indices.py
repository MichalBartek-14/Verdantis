"""
Spectral index definitions used across the pilot and monitoring scripts.
Keeping the band math in one place means the historical pilot and the
recent drought-monitoring precursor compute indices identically, so
client-facing numbers stay comparable between the two products.
"""


def ndvi_band(cube):
    """NDVI = (B08 - B04) / (B08 + B04) - vegetation vigour.
    Returns a cube with the 'bands' dimension collapsed."""
    red = cube.band("B04")
    nir = cube.band("B08")
    return (nir - red) / (nir + red)


def ndwi_band(cube):
    """NDWI = (B08 - B11) / (B08 + B11) - canopy/soil moisture proxy
    (Gao-family index, broad NIR band). Lower values indicate a drier
    signal. Returns a cube with the 'bands' dimension collapsed."""
    nir = cube.band("B08")
    swir = cube.band("B11")
    return (nir - swir) / (nir + swir)


def ndmi_band(cube):
    """NDMI = (B8A - B11) / (B8A + B11) - canopy/soil moisture proxy,
    Sentinel Hub's standard NDMI definition for Sentinel-2. Same family
    and interpretation as ndwi_band() above, but uses the narrow NIR
    band (B8A, 865nm) instead of the broad one (B08, 842nm) - the two
    are highly correlated but not identical, so NDWI and NDMI are worth
    comparing side by side rather than treating as interchangeable.
    Lower values indicate a drier signal. Returns a cube with the
    'bands' dimension collapsed."""
    nir_narrow = cube.band("B8A")
    swir = cube.band("B11")
    return (nir_narrow - swir) / (nir_narrow + swir)


def combine_as_bands(**band_cubes):
    """Re-attach a singleton 'bands' dimension to each single-index cube
    (band() / band-math collapses it) and merge them all into one
    multi-band cube, so a single download gives every requested index
    together. Call as combine_as_bands(NDVI=ndvi_band(cube),
    NDWI=ndwi_band(cube), NDMI=ndmi_band(cube), ...) - the keyword names
    become the band labels."""
    if not band_cubes:
        raise ValueError("combine_as_bands() needs at least one label=cube keyword argument.")
    labelled = [
        cube.add_dimension(name="bands", label=label, type="bands")
        for label, cube in band_cubes.items()
    ]
    merged = labelled[0]
    for cube in labelled[1:]:
        merged = merged.merge_cubes(cube)
    return merged
