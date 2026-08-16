"""
Free, keyless ERA5-based temperature data via Open-Meteo's historical
archive API (https://open-meteo.com/en/docs/historical-weather-api), which
serves ECMWF ERA5 / ERA5-Land reanalysis (blended with recent operational
data for the last few days that aren't finalised in ERA5 yet). Used
instead of the raw Copernicus Climate Data Store (the `cdsapi` package)
because that requires its own separate CDS account + API key - this
module needs neither, so the historical pilot can pull temperature
context without any extra client setup. Swap this out for `cdsapi`
later if you need other ERA5 variables or the full CDS dataset.
"""
from pathlib import Path

import pandas as pd
import requests

OPEN_METEO_ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"


def fetch_era5_monthly_temperature(lat: float, lon: float, start_date: str, end_date: str,
                                    cache_path: Path = None) -> pd.DataFrame:
    """Daily ERA5 mean 2m air temperature for [start_date, end_date]
    (inclusive ISO date strings) at (lat, lon), resampled to monthly
    means. Returns a DataFrame with columns ['month', 'mean_temp_c'],
    `month` being the first-of-month Timestamp (matching openEO's
    aggregate_temporal_period(period="month") convention, so it merges
    cleanly against a Sentinel-2 monthly composite time series).

    `cache_path`, if given, caches the raw daily pull there so repeat
    runs over the same window don't re-hit the API."""
    if cache_path is not None and Path(cache_path).exists():
        daily = pd.read_csv(cache_path, parse_dates=["date"])
    else:
        response = requests.get(
            OPEN_METEO_ARCHIVE_URL,
            params={
                "latitude": lat,
                "longitude": lon,
                "start_date": start_date,
                "end_date": end_date,
                "daily": "temperature_2m_mean",
                "timezone": "UTC",
            },
            timeout=60,
        )
        response.raise_for_status()
        payload = response.json()["daily"]
        daily = pd.DataFrame({
            "date": pd.to_datetime(payload["time"]),
            "mean_temp_c": payload["temperature_2m_mean"],
        })
        if cache_path is not None:
            cache_path = Path(cache_path)
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            daily.to_csv(cache_path, index=False)

    monthly = (
        daily.set_index("date")["mean_temp_c"]
        .resample("MS")
        .mean()
        .reset_index()
        .rename(columns={"date": "month"})
    )
    return monthly
