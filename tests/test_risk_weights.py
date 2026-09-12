import pytest

from src.risk.risk_engine import WEIGHTS


def test_weights_mapping_is_immutable():
    with pytest.raises(TypeError):
        WEIGHTS["incident_severity"] = 0.5

    with pytest.raises(TypeError):
        WEIGHTS["new_policy"] = 0.1

    with pytest.raises(TypeError):
        del WEIGHTS["incident_severity"]

    assert WEIGHTS["incident_severity"] == 0.30
    assert WEIGHTS["weather_severity"] == 0.20
