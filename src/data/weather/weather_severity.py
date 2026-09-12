"""SETU Deterministic Weather Severity Adapter (Checkpoint 17).

Translates raw and normalized Open-Meteo current weather observations
(weather_code, precipitation, wind_speed_10m, wind_gusts_10m) into a deterministic
weather_severity value in [0.0, 1.0] for consumption by the SETU Risk Engine.

Separation of Concerns:
- Data Acquisition (fetch_live_weather.py): Ingestion, batching, and local caching.
- Weather Severity Adapter (this module): Mathematical mapping, nearest-point lookup,
  and length-weighted route aggregation.
- Risk Engine (src/risk/risk_engine.py): Pure weighted risk scoring using the adapted
  weather_severity input. Formula, weights, and thresholds remain completely unchanged.

Weather Severity Semantics:
- 0.0: No adverse weather hazard (calm, clear, dry).
- 1.0: Maximum adverse weather hazard (extreme gale, violent precipitation/thunderstorm).
"""

from __future__ import annotations

import math
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

from src.impact.network_impact import haversine_km

class InvalidWeatherInputError(ValueError):
    """Raised when weather input values (WMO code, precipitation, wind speed, gusts) are invalid, missing, unsupported, or non-finite."""
    pass


# ------------------------------------------------------------------------------
# 1. Exact WMO Weather Code Contributions (Swmo in [0.0, 1.0])
# ------------------------------------------------------------------------------
WMO_CODE_SEVERITY: Dict[int, float] = {
    # Clear / Mainly Clear
    0: 0.00,   # Clear sky
    1: 0.05,   # Mainly clear
    2: 0.10,   # Partly cloudy
    3: 0.20,   # Overcast
    # Fog
    45: 0.35,  # Fog
    48: 0.40,  # Depositing rime fog
    # Drizzle
    51: 0.25,  # Light drizzle
    53: 0.35,  # Moderate drizzle
    55: 0.45,  # Dense drizzle
    56: 0.50,  # Light freezing drizzle
    57: 0.65,  # Dense freezing drizzle
    # Rain
    61: 0.30,  # Slight rain
    63: 0.55,  # Moderate rain
    65: 0.80,  # Heavy rain
    66: 0.65,  # Light freezing rain
    67: 0.90,  # Heavy freezing rain
    # Snow
    71: 0.50,  # Slight snow fall
    73: 0.70,  # Moderate snow fall
    75: 0.90,  # Heavy snow fall
    77: 0.50,  # Snow grains
    # Rain Showers
    80: 0.35,  # Slight rain showers
    81: 0.60,  # Moderate rain showers
    82: 0.85,  # Violent rain showers
    # Snow Showers
    85: 0.55,  # Slight snow showers
    86: 0.90,  # Heavy snow showers
    # Thunderstorm
    95: 0.80,  # Thunderstorm (slight or moderate)
    96: 0.90,  # Thunderstorm with slight hail
    99: 1.00,  # Thunderstorm with heavy hail
}


def _evaluate_wmo_code(code_val: Any) -> float:
    """Deterministically map a WMO weather code to [0.0, 1.0].

    Raises:
        InvalidWeatherInputError: If code_val is None, non-finite, not an integer, or not a supported WMO code.
    """
    if code_val is None:
        raise InvalidWeatherInputError("weather_code is required and cannot be None")
    if isinstance(code_val, bool):
        raise InvalidWeatherInputError(f"weather_code cannot be a boolean: {code_val!r}")

    if isinstance(code_val, float):
        if not math.isfinite(code_val):
            raise InvalidWeatherInputError(f"weather_code must be finite, got: {code_val!r}")
        if not code_val.is_integer():
            raise InvalidWeatherInputError(f"weather_code must be an integer, got non-integer float: {code_val!r}")
        c = int(code_val)
    elif isinstance(code_val, int):
        c = code_val
    elif isinstance(code_val, str):
        try:
            c = int(code_val)
        except ValueError:
            raise InvalidWeatherInputError(f"weather_code must be an integer, got: {code_val!r}")
    else:
        raise InvalidWeatherInputError(
            f"weather_code must be an integer, got type {type(code_val).__name__}: {code_val!r}"
        )

    if c not in WMO_CODE_SEVERITY:
        raise InvalidWeatherInputError(
            f"Unsupported or unknown WMO weather_code: {c}. "
            f"Supported codes: {sorted(WMO_CODE_SEVERITY.keys())}"
        )

    return WMO_CODE_SEVERITY[c]


# ------------------------------------------------------------------------------
# 2. Exact Precipitation Contribution (Sprecip in [0.0, 1.0])
# ------------------------------------------------------------------------------
# Thresholds (mm/h or current precipitation mm):
# <= 0.0 mm       -> 0.00
# (0.0, 2.5] mm   -> scaled 0.00 to 0.25 (light)
# (2.5, 10.0] mm  -> scaled 0.25 to 0.60 (moderate)
# (10.0, 25.0] mm -> scaled 0.60 to 0.90 (heavy)
# >= 25.0 mm      -> 1.00 (torrential/extreme)
def _evaluate_precipitation(precip_mm: Any) -> float:
    """Deterministically map precipitation in mm to [0.0, 1.0].

    Raises:
        InvalidWeatherInputError: If precip_mm is None, non-numeric, non-finite, or negative.
    """
    if precip_mm is None:
        raise InvalidWeatherInputError("precipitation is required and cannot be None")
    if isinstance(precip_mm, bool):
        raise InvalidWeatherInputError(f"precipitation must be a numeric value, got boolean: {precip_mm!r}")
    try:
        p = float(precip_mm)
    except (TypeError, ValueError):
        raise InvalidWeatherInputError(f"precipitation must be numeric, got: {precip_mm!r}")

    if not math.isfinite(p):
        raise InvalidWeatherInputError(f"precipitation must be finite, got non-finite value: {precip_mm!r}")
    if p < 0.0:
        raise InvalidWeatherInputError(f"precipitation cannot be negative, got: {precip_mm!r}")

    if p == 0.0:
        return 0.00
    if p <= 2.5:
        return (p / 2.5) * 0.25
    if p <= 10.0:
        return 0.25 + ((p - 2.5) / 7.5) * 0.35
    if p <= 25.0:
        return 0.60 + ((p - 10.0) / 15.0) * 0.30
    return 1.00


# ------------------------------------------------------------------------------
# 3. Exact Wind Speed Contribution (Swind in [0.0, 1.0])
# ------------------------------------------------------------------------------
# Thresholds (km/h):
# <= 15.0 km/h     -> 0.00 (calm/light breeze)
# (15.0, 40.0] km/h -> scaled 0.00 to 0.30 (moderate)
# (40.0, 70.0] km/h -> scaled 0.30 to 0.70 (strong wind / high-profile vehicle risk)
# (70.0, 90.0] km/h -> scaled 0.70 to 1.00 (gale)
# >= 90.0 km/h     -> 1.00 (storm/impassable)
def _evaluate_wind_speed(wind_kmh: Any) -> float:
    """Deterministically map 10m wind speed in km/h to [0.0, 1.0].

    Raises:
        InvalidWeatherInputError: If wind_kmh is None, non-numeric, non-finite, or negative.
    """
    if wind_kmh is None:
        raise InvalidWeatherInputError("wind_speed_10m is required and cannot be None")
    if isinstance(wind_kmh, bool):
        raise InvalidWeatherInputError(f"wind_speed_10m must be a numeric value, got boolean: {wind_kmh!r}")
    try:
        w = float(wind_kmh)
    except (TypeError, ValueError):
        raise InvalidWeatherInputError(f"wind_speed_10m must be numeric, got: {wind_kmh!r}")

    if not math.isfinite(w):
        raise InvalidWeatherInputError(f"wind_speed_10m must be finite, got non-finite value: {wind_kmh!r}")
    if w < 0.0:
        raise InvalidWeatherInputError(f"wind_speed_10m cannot be negative, got: {wind_kmh!r}")

    if w <= 15.0:
        return 0.00
    if w <= 40.0:
        return ((w - 15.0) / 25.0) * 0.30
    if w <= 70.0:
        return 0.30 + ((w - 40.0) / 30.0) * 0.40
    if w <= 90.0:
        return 0.70 + ((w - 70.0) / 20.0) * 0.30
    return 1.00


# ------------------------------------------------------------------------------
# 4. Exact Wind Gusts Contribution (Sgust in [0.0, 1.0])
# ------------------------------------------------------------------------------
# Thresholds (km/h):
# <= 25.0 km/h      -> 0.00 (calm gusts)
# (25.0, 55.0] km/h -> scaled 0.00 to 0.35 (moderate gusts)
# (55.0, 85.0] km/h -> scaled 0.35 to 0.75 (severe gusts)
# (85.0, 110.0] km/h-> scaled 0.75 to 1.00 (extreme mountain/bridge gusts)
# >= 110.0 km/h     -> 1.00 (violent storm gusts)
def _evaluate_wind_gusts(gusts_kmh: Any) -> float:
    """Deterministically map 10m wind gusts in km/h to [0.0, 1.0].

    Raises:
        InvalidWeatherInputError: If gusts_kmh is None, non-numeric, non-finite, or negative.
    """
    if gusts_kmh is None:
        raise InvalidWeatherInputError("wind_gusts_10m is required and cannot be None")
    if isinstance(gusts_kmh, bool):
        raise InvalidWeatherInputError(f"wind_gusts_10m must be a numeric value, got boolean: {gusts_kmh!r}")
    try:
        g = float(gusts_kmh)
    except (TypeError, ValueError):
        raise InvalidWeatherInputError(f"wind_gusts_10m must be numeric, got: {gusts_kmh!r}")

    if not math.isfinite(g):
        raise InvalidWeatherInputError(f"wind_gusts_10m must be finite, got non-finite value: {gusts_kmh!r}")
    if g < 0.0:
        raise InvalidWeatherInputError(f"wind_gusts_10m cannot be negative, got: {gusts_kmh!r}")

    if g <= 25.0:
        return 0.00
    if g <= 55.0:
        return ((g - 25.0) / 30.0) * 0.35
    if g <= 85.0:
        return 0.35 + ((g - 55.0) / 30.0) * 0.40
    if g <= 110.0:
        return 0.75 + ((g - 85.0) / 25.0) * 0.25
    return 1.00


# ------------------------------------------------------------------------------
# 5. Exact Combination & Clamping Rule
# ------------------------------------------------------------------------------
# Weights:
# - W_wmo    = 0.35
# - W_precip = 0.35
# - W_wind   = 0.15
# - W_gust   = 0.15
# Base weighted blend:
# S_base = 0.35 * Swmo + 0.35 * Sprecip + 0.15 * Swind + 0.15 * Sgust
# Peak hazard component:
# S_peak = max(Swmo, Sprecip, Swind, Sgust)
# Combined severity:
# S_combined = 0.60 * S_base + 0.40 * S_peak
# Output clamping:
# weather_severity = round(clamp(S_combined, 0.0, 1.0), 4)
W_WMO = 0.35
W_PRECIP = 0.35
W_WIND = 0.15
W_GUST = 0.15
BLEND_BASE = 0.60
BLEND_PEAK = 0.40


def calculate_weather_severity(weather_record: Optional[Mapping[str, Any]]) -> float:
    """Convert an Open-Meteo current weather record into a normalized weather_severity in [0.0, 1.0].

    Args:
        weather_record: Mapping containing current weather fields (or point record with 'current').
            Expected fields (under record or record['current']):
            - weather_code: int/float (valid WMO code)
            - precipitation: float (mm)
            - wind_speed_10m: float (km/h)
            - wind_gusts_10m: float (km/h)

    Returns:
        Deterministic float in [0.0, 1.0] rounded to 4 decimal places.

    Raises:
        InvalidWeatherInputError: If weather_record is missing, or any required field is missing,
            non-finite, negative, or unsupported.
    """
    if weather_record is None or not isinstance(weather_record, Mapping):
        raise InvalidWeatherInputError("weather_record must be a non-empty mapping")

    # Allow passing either the raw current dict or a full point record containing 'current'
    data = weather_record.get("current") if isinstance(weather_record.get("current"), Mapping) else weather_record
    if not isinstance(data, Mapping):
        raise InvalidWeatherInputError("weather_record data or 'current' must be a mapping")

    if "weather_code" not in data:
        raise InvalidWeatherInputError("Missing required weather field: 'weather_code'")
    s_wmo = _evaluate_wmo_code(data.get("weather_code"))

    precip_raw = data.get("precipitation") if "precipitation" in data else data.get("rain")
    if precip_raw is None and "precipitation" not in data and "rain" not in data:
        raise InvalidWeatherInputError("Missing required weather field: 'precipitation' (or 'rain')")
    s_precip = _evaluate_precipitation(precip_raw)

    if "wind_speed_10m" not in data:
        raise InvalidWeatherInputError("Missing required weather field: 'wind_speed_10m'")
    s_wind = _evaluate_wind_speed(data.get("wind_speed_10m"))

    if "wind_gusts_10m" not in data:
        raise InvalidWeatherInputError("Missing required weather field: 'wind_gusts_10m'")
    s_gust = _evaluate_wind_gusts(data.get("wind_gusts_10m"))

    s_base = (
        W_WMO * s_wmo
        + W_PRECIP * s_precip
        + W_WIND * s_wind
        + W_GUST * s_gust
    )
    s_peak = max(s_wmo, s_precip, s_wind, s_gust)

    s_combined = BLEND_BASE * s_base + BLEND_PEAK * s_peak
    clamped = max(0.0, min(1.0, s_combined))
    return round(clamped, 4)


# ------------------------------------------------------------------------------
# 6. Nearest Weather Point Resolution
# ------------------------------------------------------------------------------
def resolve_nearest_weather_point(
    lat: float,
    lon: float,
    weather_points: Iterable[Mapping[str, Any]],
) -> Dict[str, Any]:
    """Find the nearest weather sampling point to given coordinates using great-circle distance.

    Args:
        lat: Target latitude in [-90.0, 90.0].
        lon: Target longitude in [-180.0, 180.0].
        weather_points: Iterable of weather point dictionaries with 'latitude' and 'longitude'.

    Returns:
        Dictionary of the nearest weather point record, with 'distance_km' appended.

    Raises:
        ValueError: If weather_points is empty or contains no valid coordinate points.
    """
    best_point: Optional[Dict[str, Any]] = None
    best_dist = float("inf")

    for pt in weather_points:
        if not isinstance(pt, Mapping):
            continue
        p_lat = pt.get("latitude")
        p_lon = pt.get("longitude")
        if p_lat is None or p_lon is None:
            continue
        try:
            d_km = haversine_km(float(lat), float(lon), float(p_lat), float(p_lon))
        except (TypeError, ValueError):
            continue

        if d_km < best_dist:
            best_dist = d_km
            best_point = dict(pt)

    if best_point is None:
        raise ValueError("Cannot resolve nearest weather point from empty or invalid weather_points collection")

    best_point["distance_km"] = round(best_dist, 4)
    return best_point


# ------------------------------------------------------------------------------
# 7. Route Weather Aggregation (Length-Weighted Mean ONLY)
# ------------------------------------------------------------------------------
def aggregate_route_weather_severity(
    segments: Iterable[Mapping[str, Any]],
    weather_points: Iterable[Mapping[str, Any]],
) -> float:
    """Compute the length-weighted mean weather severity across a collection of route segments.

    Per Checkpoint 17 specification:
    - Uses ONLY length-weighted mean weather severity.
    - Does NOT implement worst-case aggregation.

    Args:
        segments: Iterable of route segment dictionaries. Each segment should provide
            length ('segment_length_km') and coordinates (start/end or midpoint).
        weather_points: Iterable of weather point dictionaries with live or cached weather observations.

    Returns:
        Deterministic float in [0.0, 1.0] rounded to 4 decimal places.
    """
    if segments is None:
        return 0.0

    seg_list = list(segments)
    if not seg_list:
        return 0.0

    pts_list = list(weather_points)
    if not pts_list:
        return 0.0

    # Pre-cache weather severity per point to prevent redundant calculations
    point_severity_cache: Dict[str, float] = {}
    for pt in pts_list:
        pid = str(pt.get("weather_point_id", f"{pt.get('latitude')}_{pt.get('longitude')}"))
        point_severity_cache[pid] = calculate_weather_severity(pt)

    total_length_km = 0.0
    weighted_severity_sum = 0.0

    for seg in seg_list:
        if not isinstance(seg, Mapping):
            continue

        length_km = float(seg.get("segment_length_km", 1.0))
        if length_km <= 0.0:
            length_km = 1.0

        # Resolve representative segment midpoint
        if (
            "start_latitude" in seg and "start_longitude" in seg
            and "end_latitude" in seg and "end_longitude" in seg
            and seg["start_latitude"] is not None and seg["start_longitude"] is not None
            and seg["end_latitude"] is not None and seg["end_longitude"] is not None
        ):
            mid_lat = (float(seg["start_latitude"]) + float(seg["end_latitude"])) / 2.0
            mid_lon = (float(seg["start_longitude"]) + float(seg["end_longitude"])) / 2.0
        elif "latitude" in seg and "longitude" in seg and seg["latitude"] is not None and seg["longitude"] is not None:
            mid_lat = float(seg["latitude"])
            mid_lon = float(seg["longitude"])
        else:
            # Fallback to 0.0 if no coordinates are present
            continue

        nearest_pt = resolve_nearest_weather_point(mid_lat, mid_lon, pts_list)
        pid = str(nearest_pt.get("weather_point_id", f"{nearest_pt.get('latitude')}_{nearest_pt.get('longitude')}"))
        seg_severity = point_severity_cache.get(pid, calculate_weather_severity(nearest_pt))

        weighted_severity_sum += seg_severity * length_km
        total_length_km += length_km

    if total_length_km <= 0.0:
        return 0.0

    mean_severity = weighted_severity_sum / total_length_km
    clamped = max(0.0, min(1.0, mean_severity))
    return round(clamped, 4)


# ------------------------------------------------------------------------------
# 8. Risk Context Integration Helper
# ------------------------------------------------------------------------------
def build_weather_risk_context(
    target: Mapping[str, Any],
    weather_points: Iterable[Mapping[str, Any]],
    base_risk_context: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Integrate adapted weather_severity into a complete risk_context mapping.

    Args:
        target: A candidate route (containing 'segments'), a single segment, or coordinate mapping.
        weather_points: Iterable of weather point dictionaries with observations.
        base_risk_context: Optional existing risk context containing the other required
            fields (incident_severity, accessibility_score, road_condition_score,
            network_criticality, current_delay_ratio).

    Returns:
        A dictionary with 'weather_severity' populated from adapted weather data,
        preserving all existing fields in base_risk_context.
    """
    pts_list = list(weather_points)

    # Determine if target is a route with segments or a single point/segment
    if "segments" in target and isinstance(target["segments"], list) and target["segments"]:
        computed_severity = aggregate_route_weather_severity(target["segments"], pts_list)
    elif "latitude" in target and "longitude" in target and target["latitude"] is not None and target["longitude"] is not None:
        nearest = resolve_nearest_weather_point(float(target["latitude"]), float(target["longitude"]), pts_list)
        computed_severity = calculate_weather_severity(nearest)
    else:
        computed_severity = aggregate_route_weather_severity([target], pts_list)

    result = dict(base_risk_context) if base_risk_context is not None else {}
    result["weather_severity"] = computed_severity
    return result
