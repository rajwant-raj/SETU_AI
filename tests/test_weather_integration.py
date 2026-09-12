"""Tests for Checkpoint 17 — Live Weather Integration into Risk.

Verifies:
- Exact deterministic WMO weather code mapping
- Exact precipitation threshold scaling
- Exact wind speed and gust threshold scaling
- Exact combined severity calculation and clamping
- Nearest weather-point spatial lookup
- Route weather aggregation using ONLY length-weighted mean
- Cache hit / stale / missing cache resolution
- Mocked Open-Meteo API response handling (zero live network calls)
- HTTP 429 and network error fallback to cache
- Nominal fallback (severity 0.0, is_live=False, NOMINAL_FALLBACK)
- Strict mode raising LiveWeatherUnavailableError
- Risk Engine integration with adapted weather_severity
- ADVERSE_WEATHER (>= 0.75) and MODERATE_WEATHER_RISK (>= 0.50) triggers
- Omission of weather reasons when severity < 0.50
- Immutable Risk Engine policy weights (0.20 for weather_severity) preserved
"""

import copy
import json
from unittest.mock import MagicMock, patch
import pytest

from src.data.weather import (
    BLEND_BASE,
    BLEND_PEAK,
    InvalidWeatherInputError,
    LiveWeatherUnavailableError,
    WMO_CODE_SEVERITY,
    W_GUST,
    W_PRECIP,
    W_WIND,
    W_WMO,
    aggregate_route_weather_severity,
    build_weather_risk_context,
    calculate_weather_severity,
    get_live_weather_snapshot,
    load_cached_weather,
    resolve_nearest_weather_point,
)
from src.data.weather.weather_severity import (
    _evaluate_precipitation,
    _evaluate_wind_gusts,
    _evaluate_wind_speed,
    _evaluate_wmo_code,
)
from src.risk.risk_engine import WEIGHTS, calculate_risk


# ==============================================================================
# 1. Exact Threshold & Mapping Tests
# ==============================================================================

def test_exact_wmo_code_mappings():
    """Verify exact WMO code contributions against defined table."""
    assert _evaluate_wmo_code(0) == 0.00   # Clear sky
    assert _evaluate_wmo_code(1) == 0.05   # Mainly clear
    assert _evaluate_wmo_code(2) == 0.10   # Partly cloudy
    assert _evaluate_wmo_code(3) == 0.20   # Overcast
    assert _evaluate_wmo_code(45) == 0.35  # Fog
    assert _evaluate_wmo_code(51) == 0.25  # Light drizzle
    assert _evaluate_wmo_code(61) == 0.30  # Slight rain
    assert _evaluate_wmo_code(63) == 0.55  # Moderate rain
    assert _evaluate_wmo_code(65) == 0.80  # Heavy rain
    assert _evaluate_wmo_code(71) == 0.50  # Slight snow
    assert _evaluate_wmo_code(82) == 0.85  # Violent showers
    assert _evaluate_wmo_code(95) == 0.80  # Thunderstorm
    assert _evaluate_wmo_code(99) == 1.00  # Thunderstorm with heavy hail


def test_unknown_wmo_code_rejection():
    """Verify unknown, unsupported, non-integer, or non-finite WMO codes raise InvalidWeatherInputError."""
    # Unknown WMO codes
    with pytest.raises(InvalidWeatherInputError, match="Unsupported or unknown WMO"):
        _evaluate_wmo_code(999)

    with pytest.raises(InvalidWeatherInputError, match="Unsupported or unknown WMO"):
        _evaluate_wmo_code(42)

    with pytest.raises(InvalidWeatherInputError, match="Unsupported or unknown WMO"):
        _evaluate_wmo_code(-1)

    # Missing / None
    with pytest.raises(InvalidWeatherInputError, match="weather_code is required"):
        _evaluate_wmo_code(None)

    # Non-integer / non-numeric
    with pytest.raises(InvalidWeatherInputError):
        _evaluate_wmo_code("invalid_code")

    with pytest.raises(InvalidWeatherInputError):
        _evaluate_wmo_code(True)

    with pytest.raises(InvalidWeatherInputError):
        _evaluate_wmo_code(float("nan"))

    with pytest.raises(InvalidWeatherInputError):
        _evaluate_wmo_code(float("inf"))

    with pytest.raises(InvalidWeatherInputError):
        _evaluate_wmo_code(2.7)

    # End-to-end rejection via calculate_weather_severity
    with pytest.raises(InvalidWeatherInputError, match="Unsupported or unknown WMO"):
        calculate_weather_severity({
            "weather_code": 999,
            "precipitation": 0.0,
            "wind_speed_10m": 10.0,
            "wind_gusts_10m": 15.0,
        })


def test_exact_precipitation_thresholds():
    """Verify exact precipitation piecewise scaling."""
    assert _evaluate_precipitation(0.0) == 0.00

    # (0, 2.5] -> scaled 0.0 to 0.25
    assert pytest.approx(_evaluate_precipitation(2.5), abs=1e-6) == 0.25
    assert pytest.approx(_evaluate_precipitation(1.25), abs=1e-6) == 0.125

    # (2.5, 10.0] -> scaled 0.25 to 0.60
    assert pytest.approx(_evaluate_precipitation(10.0), abs=1e-6) == 0.60
    assert pytest.approx(_evaluate_precipitation(6.25), abs=1e-6) == 0.425

    # (10.0, 25.0] -> scaled 0.60 to 0.90
    assert pytest.approx(_evaluate_precipitation(25.0), abs=1e-6) == 0.90
    assert pytest.approx(_evaluate_precipitation(17.5), abs=1e-6) == 0.75

    # >= 25.0 -> 1.00
    assert _evaluate_precipitation(30.0) == 1.00
    assert _evaluate_precipitation(100.0) == 1.00


def test_exact_wind_speed_thresholds():
    """Verify exact 10m wind speed scaling."""
    assert _evaluate_wind_speed(0.0) == 0.00
    assert _evaluate_wind_speed(15.0) == 0.00

    # (15, 40] -> scaled 0.0 to 0.30
    assert pytest.approx(_evaluate_wind_speed(40.0), abs=1e-6) == 0.30
    assert pytest.approx(_evaluate_wind_speed(27.5), abs=1e-6) == 0.15

    # (40, 70] -> scaled 0.30 to 0.70
    assert pytest.approx(_evaluate_wind_speed(70.0), abs=1e-6) == 0.70
    assert pytest.approx(_evaluate_wind_speed(55.0), abs=1e-6) == 0.50

    # (70, 90] -> scaled 0.70 to 1.00
    assert pytest.approx(_evaluate_wind_speed(90.0), abs=1e-6) == 1.00
    assert pytest.approx(_evaluate_wind_speed(80.0), abs=1e-6) == 0.85

    # >= 90.0 -> 1.00
    assert _evaluate_wind_speed(120.0) == 1.00


def test_exact_wind_gust_thresholds():
    """Verify exact 10m wind gust scaling."""
    assert _evaluate_wind_gusts(0.0) == 0.00
    assert _evaluate_wind_gusts(25.0) == 0.00

    # (25, 55] -> scaled 0.0 to 0.35
    assert pytest.approx(_evaluate_wind_gusts(55.0), abs=1e-6) == 0.35
    assert pytest.approx(_evaluate_wind_gusts(40.0), abs=1e-6) == 0.175

    # (55, 85] -> scaled 0.35 to 0.75
    assert pytest.approx(_evaluate_wind_gusts(85.0), abs=1e-6) == 0.75
    assert pytest.approx(_evaluate_wind_gusts(70.0), abs=1e-6) == 0.55

    # (85, 110] -> scaled 0.75 to 1.00
    assert pytest.approx(_evaluate_wind_gusts(110.0), abs=1e-6) == 1.00
    assert pytest.approx(_evaluate_wind_gusts(97.5), abs=1e-6) == 0.875

    # >= 110.0 -> 1.00
    assert _evaluate_wind_gusts(150.0) == 1.00


def test_non_finite_and_invalid_continuous_weather_inputs():
    """Verify missing, non-finite, negative, or invalid continuous inputs raise InvalidWeatherInputError."""
    # Precipitation validation
    with pytest.raises(InvalidWeatherInputError, match="precipitation is required"):
        _evaluate_precipitation(None)
    with pytest.raises(InvalidWeatherInputError, match="precipitation cannot be negative"):
        _evaluate_precipitation(-5.0)
    with pytest.raises(InvalidWeatherInputError, match="precipitation must be finite"):
        _evaluate_precipitation(float("nan"))
    with pytest.raises(InvalidWeatherInputError, match="precipitation must be finite"):
        _evaluate_precipitation(float("inf"))
    with pytest.raises(InvalidWeatherInputError, match="precipitation must be a numeric"):
        _evaluate_precipitation(True)

    # Wind speed validation
    with pytest.raises(InvalidWeatherInputError, match="wind_speed_10m is required"):
        _evaluate_wind_speed(None)
    with pytest.raises(InvalidWeatherInputError, match="wind_speed_10m cannot be negative"):
        _evaluate_wind_speed(-10.0)
    with pytest.raises(InvalidWeatherInputError, match="wind_speed_10m must be finite"):
        _evaluate_wind_speed(float("nan"))
    with pytest.raises(InvalidWeatherInputError, match="wind_speed_10m must be finite"):
        _evaluate_wind_speed(float("-inf"))

    # Wind gusts validation
    with pytest.raises(InvalidWeatherInputError, match="wind_gusts_10m is required"):
        _evaluate_wind_gusts(None)
    with pytest.raises(InvalidWeatherInputError, match="wind_gusts_10m cannot be negative"):
        _evaluate_wind_gusts(-15.0)
    with pytest.raises(InvalidWeatherInputError, match="wind_gusts_10m must be finite"):
        _evaluate_wind_gusts(float("nan"))

    # Missing fields in weather_record
    with pytest.raises(InvalidWeatherInputError, match="Missing required weather field: 'weather_code'"):
        calculate_weather_severity({"precipitation": 0.0, "wind_speed_10m": 10.0, "wind_gusts_10m": 15.0})

    with pytest.raises(InvalidWeatherInputError, match="Missing required weather field: 'precipitation'"):
        calculate_weather_severity({"weather_code": 0, "wind_speed_10m": 10.0, "wind_gusts_10m": 15.0})

    with pytest.raises(InvalidWeatherInputError, match="Missing required weather field: 'wind_speed_10m'"):
        calculate_weather_severity({"weather_code": 0, "precipitation": 0.0, "wind_gusts_10m": 15.0})

    with pytest.raises(InvalidWeatherInputError, match="Missing required weather field: 'wind_gusts_10m'"):
        calculate_weather_severity({"weather_code": 0, "precipitation": 0.0, "wind_speed_10m": 10.0})


def test_exact_combined_severity_calculation():
    """Verify exact formula combining WMO, precipitation, wind, gusts, and peak factor."""
    # Calm / Clear condition
    calm = {
        "weather_code": 0,
        "precipitation": 0.0,
        "wind_speed_10m": 10.0,
        "wind_gusts_10m": 20.0,
    }
    assert calculate_weather_severity(calm) == 0.0000

    # Severe Storm condition
    storm = {
        "weather_code": 95,
        "precipitation": 30.0,
        "wind_speed_10m": 95.0,
        "wind_gusts_10m": 120.0,
    }
    assert calculate_weather_severity(storm) == 0.9580

    # Extreme severe thunderstorm (WMO 99, massive precip and gale)
    extreme = {
        "weather_code": 99,
        "precipitation": 150.0,
        "wind_speed_10m": 120.0,
        "wind_gusts_10m": 160.0,
    }
    assert calculate_weather_severity(extreme) == 1.0000


def test_output_clamping():
    """Verify strict clamping of weather_severity to [0.0, 1.0] across extreme inputs."""
    extreme_high = {
        "weather_code": 99,
        "precipitation": 9999.0,
        "wind_speed_10m": 9999.0,
        "wind_gusts_10m": 9999.0,
    }
    val_high = calculate_weather_severity(extreme_high)
    assert val_high <= 1.0
    assert val_high == 1.0


# ==============================================================================
# 2. Spatial Mapping & Route Aggregation
# ==============================================================================

@pytest.fixture
def weather_sampling_points():
    """Subset of representative weather points for the corridor."""
    return [
        {
            "weather_point_id": "WX-001",
            "latitude": 26.10,
            "longitude": 91.70,
            "current": {
                "weather_code": 0,
                "precipitation": 0.0,
                "wind_speed_10m": 10.0,
                "wind_gusts_10m": 15.0,
            },
        },
        {
            "weather_point_id": "WX-002",
            "latitude": 26.20,
            "longitude": 91.80,
            "current": {
                "weather_code": 65,  # Heavy rain
                "precipitation": 20.0,
                "wind_speed_10m": 45.0,
                "wind_gusts_10m": 60.0,
            },
        },
    ]


def test_nearest_weather_point_lookup(weather_sampling_points):
    """Verify coordinate resolves to closest weather point via great-circle distance."""
    # Coordinate closer to WX-001 (26.10, 91.70)
    pt1 = resolve_nearest_weather_point(26.11, 91.71, weather_sampling_points)
    assert pt1["weather_point_id"] == "WX-001"
    assert pt1["distance_km"] > 0.0

    # Coordinate closer to WX-002 (26.20, 91.80)
    pt2 = resolve_nearest_weather_point(26.19, 91.79, weather_sampling_points)
    assert pt2["weather_point_id"] == "WX-002"


def test_length_weighted_route_weather_aggregation(weather_sampling_points):
    """Verify route weather aggregation uses length-weighted mean and NOT worst-case."""
    # Segment 1 (length 10km) near WX-001 (calm: severity ~0.0)
    # Segment 2 (length 30km) near WX-002 (heavy rain: severity S2)
    s1_severity = calculate_weather_severity(weather_sampling_points[0])
    s2_severity = calculate_weather_severity(weather_sampling_points[1])
    assert s1_severity == 0.0
    assert s2_severity > 0.60

    segments = [
        {
            "segment_id": "seg_1",
            "start_latitude": 26.10,
            "start_longitude": 91.70,
            "end_latitude": 26.11,
            "end_longitude": 91.71,
            "segment_length_km": 10.0,
        },
        {
            "segment_id": "seg_2",
            "start_latitude": 26.19,
            "start_longitude": 91.79,
            "end_latitude": 26.20,
            "end_longitude": 91.80,
            "segment_length_km": 30.0,
        },
    ]

    expected_mean = round((s1_severity * 10.0 + s2_severity * 30.0) / 40.0, 4)
    actual_mean = aggregate_route_weather_severity(segments, weather_sampling_points)

    assert actual_mean == expected_mean
    # Confirm it is NOT worst-case
    assert actual_mean < s2_severity


# ==============================================================================
# 3. Cache & Fallback State Tests
# ==============================================================================

def test_cache_hit_retrieves_snapshot(tmp_path):
    """Verify load_cached_weather loads valid file within TTL."""
    cache_file = tmp_path / "live_weather.json"
    payload = {
        "fetched_at": "2026-09-13T04:00:00+00:00",
        "source": "Open-Meteo Forecast API",
        "points": [
            {
                "weather_point_id": "WX-001",
                "current": {
                    "weather_code": 0,
                    "precipitation": 0.0,
                    "wind_speed_10m": 5.0,
                    "wind_gusts_10m": 10.0,
                },
            }
        ],
    }
    with cache_file.open("w", encoding="utf-8") as f:
        json.dump(payload, f)

    cached = load_cached_weather(cache_file=cache_file)
    assert cached is not None
    assert cached["source"] == "Open-Meteo Forecast API"
    assert len(cached["points"]) == 1


def test_cache_miss_or_stale(tmp_path):
    """Verify stale or missing cache returns None."""
    missing_file = tmp_path / "non_existent.json"
    assert load_cached_weather(cache_file=missing_file) is None

    # Stale cache
    stale_file = tmp_path / "stale_weather.json"
    stale_payload = {
        "fetched_at": "2020-01-01T00:00:00+00:00",
        "points": [],
    }
    with stale_file.open("w", encoding="utf-8") as f:
        json.dump(stale_payload, f)

    # With max_age_seconds=60, a 2020 timestamp is stale
    assert load_cached_weather(cache_file=stale_file, max_age_seconds=60) is None


def test_mocked_api_response_updates_cache(tmp_path):
    """Verify live fetch with mocked requests updates cache and returns LIVE state."""
    cache_file = tmp_path / "live_weather.json"
    mock_response = MagicMock()
    mock_response.json.return_value = [
        {
            "latitude": 26.10,
            "longitude": 91.70,
            "current": {
                "weather_code": 2,
                "precipitation": 0.0,
                "wind_speed_10m": 12.0,
                "wind_gusts_10m": 18.0,
            },
        }
    ]
    mock_response.raise_for_status.return_value = None

    points_mock = [{"weather_point_id": "WX-001", "latitude": 26.10, "longitude": 91.70}]

    with patch("requests.get", return_value=mock_response):
        snapshot = get_live_weather_snapshot(
            points=points_mock,
            cache_file=cache_file,
            allow_network=True,
        )

    assert snapshot["state"] == "LIVE"
    assert snapshot["status"] == "LIVE"
    assert snapshot["is_live"] is True
    assert cache_file.exists()


def test_network_failure_falls_back_to_cache(tmp_path):
    """Verify that on HTTP 429 or network error, valid cached snapshot is returned with CACHED state."""
    cache_file = tmp_path / "live_weather.json"
    cached_payload = {
        "fetched_at": "2026-09-13T04:00:00+00:00",
        "source": "Open-Meteo Forecast API",
        "points": [
            {
                "weather_point_id": "WX-001",
                "current": {
                    "weather_code": 3,
                    "precipitation": 0.0,
                    "wind_speed_10m": 10.0,
                    "wind_gusts_10m": 15.0,
                },
            }
        ],
    }
    with cache_file.open("w", encoding="utf-8") as f:
        json.dump(cached_payload, f)

    with patch("requests.get", side_effect=Exception("HTTP 429 Too Many Requests")):
        snapshot = get_live_weather_snapshot(
            points=[{"weather_point_id": "WX-001", "latitude": 26.10, "longitude": 91.70}],
            cache_file=cache_file,
            allow_network=True,
            max_cache_age_seconds=86400 * 365,
        )

    assert snapshot["state"] == "CACHED"
    assert snapshot["status"] == "CACHED"
    assert snapshot["is_live"] is False
    assert len(snapshot["points"]) == 1


def test_nominal_fallback_when_cache_missing(tmp_path):
    """Verify nominal fallback returns severity 0.0, is_live=False, and NOMINAL_FALLBACK state."""
    cache_file = tmp_path / "empty_dir" / "live_weather.json"

    snapshot = get_live_weather_snapshot(
        points=[{"weather_point_id": "WX-001", "latitude": 26.10, "longitude": 91.70}],
        cache_file=cache_file,
        allow_network=False,
    )

    assert snapshot["state"] == "NOMINAL_FALLBACK"
    assert snapshot["status"] == "NOMINAL_FALLBACK"
    assert snapshot["is_live"] is False
    assert "Unverified" in snapshot["notes"]

    # Severity of nominal point is strictly 0.0
    pt = snapshot["points"][0]
    assert calculate_weather_severity(pt) == 0.0


def test_explicit_machine_readable_fallback_states(tmp_path):
    """Verify machine-readable state explicitly distinguishes LIVE, CACHED, and NOMINAL_FALLBACK."""
    cache_file = tmp_path / "weather_states.json"
    pts = [{"weather_point_id": "WX-001", "latitude": 26.10, "longitude": 91.70}]

    # 1. LIVE state
    mock_resp = MagicMock()
    mock_resp.json.return_value = [
        {
            "latitude": 26.10,
            "longitude": 91.70,
            "current": {
                "weather_code": 0,
                "precipitation": 0.0,
                "wind_speed_10m": 5.0,
                "wind_gusts_10m": 10.0,
            },
        }
    ]
    mock_resp.raise_for_status.return_value = None

    with patch("requests.get", return_value=mock_resp):
        live_snap = get_live_weather_snapshot(points=pts, cache_file=cache_file, allow_network=True)
    assert live_snap["state"] == "LIVE"
    assert live_snap["is_live"] is True

    # 2. CACHED state (network disabled, cache exists)
    cached_snap = get_live_weather_snapshot(points=pts, cache_file=cache_file, allow_network=False)
    assert cached_snap["state"] == "CACHED"
    assert cached_snap["is_live"] is False

    # 3. NOMINAL_FALLBACK state (cache missing, network disabled)
    missing_cache = tmp_path / "missing_cache.json"
    nominal_snap = get_live_weather_snapshot(points=pts, cache_file=missing_cache, allow_network=False)
    assert nominal_snap["state"] == "NOMINAL_FALLBACK"
    assert nominal_snap["is_live"] is False

    # Semantic difference: CACHED and NOMINAL_FALLBACK have different states despite same is_live=False
    assert cached_snap["is_live"] == nominal_snap["is_live"] == False
    assert cached_snap["state"] != nominal_snap["state"]
    assert cached_snap["state"] == "CACHED"
    assert nominal_snap["state"] == "NOMINAL_FALLBACK"


def test_strict_mode_raises_when_weather_unavailable(tmp_path):
    """Verify strict mode raises LiveWeatherUnavailableError if live & cache are unavailable."""
    cache_file = tmp_path / "no_cache.json"

    with pytest.raises(LiveWeatherUnavailableError, match="Live weather is unavailable"):
        get_live_weather_snapshot(
            points=[],
            cache_file=cache_file,
            allow_network=False,
            strict=True,
        )



# ==============================================================================
# 4. Risk Engine Integration Tests
# ==============================================================================

def test_risk_engine_integration_adverse_weather():
    """Verify adapted weather_severity >= 0.75 triggers ADVERSE_WEATHER in Risk Engine."""
    severe_weather = {
        "weather_code": 95,
        "precipitation": 30.0,
        "wind_speed_10m": 90.0,
        "wind_gusts_10m": 115.0,
    }
    severity = calculate_weather_severity(severe_weather)
    assert severity >= 0.75

    risk_inputs = {
        "incident_severity": 0.50,
        "accessibility_score": 0.90,
        "weather_severity": severity,
        "road_condition_score": 0.80,
        "network_criticality": 0.50,
        "current_delay_ratio": 0.10,
    }

    result = calculate_risk(risk_inputs)
    assert "ADVERSE_WEATHER" in result["reason_codes"]
    assert "Adverse weather conditions" in result["reasons"]


def test_risk_engine_integration_moderate_weather():
    """Verify adapted weather_severity between 0.50 and 0.749 triggers MODERATE_WEATHER_RISK."""
    moderate_weather = {
        "weather_code": 63,  # Moderate rain
        "precipitation": 12.0,
        "wind_speed_10m": 35.0,
        "wind_gusts_10m": 45.0,
    }
    severity = calculate_weather_severity(moderate_weather)
    assert 0.50 <= severity < 0.75

    risk_inputs = {
        "incident_severity": 0.20,
        "accessibility_score": 0.90,
        "weather_severity": severity,
        "road_condition_score": 0.90,
        "network_criticality": 0.30,
        "current_delay_ratio": 0.05,
    }

    result = calculate_risk(risk_inputs)
    assert "MODERATE_WEATHER_RISK" in result["reason_codes"]
    assert "Moderate weather conditions" in result["reasons"]


def test_risk_engine_omission_when_weather_below_moderate():
    """Verify weather reasons are omitted when weather_severity < 0.50."""
    mild_weather = {
        "weather_code": 2,  # Partly cloudy
        "precipitation": 0.5,
        "wind_speed_10m": 12.0,
        "wind_gusts_10m": 18.0,
    }
    severity = calculate_weather_severity(mild_weather)
    assert severity < 0.50

    risk_inputs = {
        "incident_severity": 0.20,
        "accessibility_score": 0.90,
        "weather_severity": severity,
        "road_condition_score": 0.90,
        "network_criticality": 0.30,
        "current_delay_ratio": 0.05,
    }

    result = calculate_risk(risk_inputs)
    assert "ADVERSE_WEATHER" not in result["reason_codes"]
    assert "MODERATE_WEATHER_RISK" not in result["reason_codes"]


def test_risk_engine_policy_weights_unchanged():
    """Verify Risk Engine immutable policy weight for weather_severity is strictly 0.20."""
    assert WEIGHTS["weather_severity"] == 0.20
    assert sum(WEIGHTS.values()) == 1.00


def test_build_weather_risk_context_helper(weather_sampling_points):
    """Verify build_weather_risk_context populates weather_severity while preserving other fields."""
    base_context = {
        "incident_severity": 0.60,
        "accessibility_score": 0.70,
        "road_condition_score": 0.80,
        "network_criticality": 0.40,
        "current_delay_ratio": 0.15,
    }
    route = {
        "route_id": "r1",
        "segments": [
            {
                "segment_id": "s1",
                "start_latitude": 26.10,
                "start_longitude": 91.70,
                "end_latitude": 26.11,
                "end_longitude": 91.71,
                "segment_length_km": 10.0,
            }
        ],
    }
    enriched = build_weather_risk_context(route, weather_sampling_points, base_context)

    assert "weather_severity" in enriched
    assert isinstance(enriched["weather_severity"], float)
    assert enriched["incident_severity"] == 0.60
    assert enriched["accessibility_score"] == 0.70
    assert enriched["road_condition_score"] == 0.80
    assert enriched["network_criticality"] == 0.40
    assert enriched["current_delay_ratio"] == 0.15
