"""SETU Weather Data & Severity Adapter Package (Checkpoint 17).

Provides live weather fetching, local caching, deterministic weather severity
adaptation, and route weather aggregation for SETU Risk Engine.
"""

from src.data.weather.fetch_live_weather import (
    LiveWeatherUnavailableError,
    fetch_live_weather,
    get_live_weather_snapshot,
    load_cached_weather,
    load_points,
    normalize_response,
)
from src.data.weather.weather_severity import (
    BLEND_BASE,
    BLEND_PEAK,
    InvalidWeatherInputError,
    WMO_CODE_SEVERITY,
    W_GUST,
    W_PRECIP,
    W_WIND,
    W_WMO,
    aggregate_route_weather_severity,
    build_weather_risk_context,
    calculate_weather_severity,
    resolve_nearest_weather_point,
)

__all__ = [
    "calculate_weather_severity",
    "resolve_nearest_weather_point",
    "aggregate_route_weather_severity",
    "build_weather_risk_context",
    "get_live_weather_snapshot",
    "load_cached_weather",
    "load_points",
    "fetch_live_weather",
    "normalize_response",
    "LiveWeatherUnavailableError",
    "InvalidWeatherInputError",
    "WMO_CODE_SEVERITY",
    "W_WMO",
    "W_PRECIP",
    "W_WIND",
    "W_GUST",
    "BLEND_BASE",
    "BLEND_PEAK",
]

