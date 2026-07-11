"""Tests for cca_controller.py."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from custom_components.pi_thermostat.cca_controller import CCAControllerStrategy, CCAState
from custom_components.pi_thermostat.config import resolve
from custom_components.pi_thermostat.const import CCAForecastUnavailableMode, ControlMode


def _resolved(**overrides: object):
    """Build a resolved CCA configuration for unit tests."""

    options = {
        "control_mode": ControlMode.CCA,
        "cca_cooling_enable_entity": "binary_sensor.cooling_enabled",
        "cca_weather_entity": "weather.home",
    }
    options.update(overrides)
    return resolve(options)


class TestParseForecastDate:
    """Unit tests for forecast date parsing helpers."""

    def test_accepts_datetime(self) -> None:
        """Datetime objects are converted to dates."""

        value = datetime(2026, 7, 1, 12, 0, tzinfo=UTC)

        assert CCAControllerStrategy._parse_forecast_date(value) == date(2026, 7, 1)

    def test_accepts_date(self) -> None:
        """Date objects are returned unchanged."""

        value = date(2026, 7, 2)

        assert CCAControllerStrategy._parse_forecast_date(value) == value

    def test_accepts_iso_string_with_z(self) -> None:
        """ISO datetime strings with trailing Z are supported."""

        assert CCAControllerStrategy._parse_forecast_date("2026-07-03T00:00:00Z") == date(2026, 7, 3)

    def test_rejects_invalid_values(self) -> None:
        """Malformed or unsupported values return None."""

        assert CCAControllerStrategy._parse_forecast_date("not-a-date") is None
        assert CCAControllerStrategy._parse_forecast_date(123) is None


class TestForecastExtraction:
    """Unit tests for forecast payload extraction helpers."""

    def test_extracts_high_and_low(self) -> None:
        """Numeric forecast values are converted to floats."""

        forecast = {"temperature": "31.5", "templow": 19}

        assert CCAControllerStrategy._extract_forecast_high(forecast) == 31.5
        assert CCAControllerStrategy._extract_forecast_low(forecast) == 19.0

    def test_invalid_values_return_none(self) -> None:
        """Missing or invalid forecast temperatures are ignored."""

        assert CCAControllerStrategy._extract_forecast_high({"temperature": "bad"}) is None
        assert CCAControllerStrategy._extract_forecast_low({"templow": None}) is None


class TestValidForecasts:
    """Unit tests for forecast filtering and sorting."""

    def test_skips_malformed_entries_and_honors_horizon(self) -> None:
        """Only valid forecast tuples are kept, sorted, and truncated."""

        controller = CCAControllerStrategy()
        forecasts = [
            {"datetime": "2026-07-03T12:00:00+00:00", "temperature": 30.0, "templow": 20.0},
            {"datetime": "bad-date", "temperature": 33.0, "templow": 22.0},
            {"date": "2026-07-01", "temperature": 28.0, "templow": 18.0},
            {"date": "2026-07-02", "temperature": None, "templow": 19.0},
            {"date": "2026-07-02", "temperature": 29.0, "templow": 19.0},
        ]

        valid = controller._valid_forecasts(forecasts, horizon_days=2)

        assert valid == [
            (date(2026, 7, 1), 28.0, 18.0),
            (date(2026, 7, 2), 29.0, 19.0),
        ]


class TestCompute:
    """Unit tests for CCA compute behavior."""

    def test_forecast_unavailable_hold_keeps_last_auto_output(self) -> None:
        """Hold mode preserves the last automatic output when forecasts are unavailable."""

        controller = CCAControllerStrategy()
        controller.restore_state(CCAState(charge_estimate=25.0, last_auto_output=17.0, last_heat_score=40.0, status="active"))

        result = controller.compute(
            _resolved(cca_forecast_unavailable_mode=CCAForecastUnavailableMode.HOLD),
            cooling_enabled=True,
            forecasts=None,
        )

        assert result.output == 17.0
        assert result.status == "forecast_hold"
        assert result.current_mode == "cooling"
        assert result.state.last_auto_output == 17.0

    def test_forecast_unavailable_shutdown_zeroes_output(self) -> None:
        """Shutdown mode commands zero output when forecasts are unavailable."""

        controller = CCAControllerStrategy()
        controller.restore_state(CCAState(charge_estimate=30.0, last_auto_output=12.0, last_heat_score=35.0, status="active"))

        result = controller.compute(
            _resolved(cca_forecast_unavailable_mode=CCAForecastUnavailableMode.SHUTDOWN),
            cooling_enabled=True,
            forecasts=None,
        )

        assert result.output == 0.0
        assert result.status == "forecast_unavailable"
        assert result.current_mode == "off"
        assert result.state.last_auto_output == 0.0

    def test_disabled_cooling_preserves_last_update_timestamp(self) -> None:
        """Inactive CCA refreshes do not consume another automatic control step."""

        controller = CCAControllerStrategy()
        controller.restore_state(
            CCAState(
                charge_estimate=30.0,
                last_auto_output=12.0,
                last_heat_score=35.0,
                last_update_iso="2026-07-01T00:00:00+00:00",
                status="active",
            )
        )

        result = controller.compute(
            _resolved(),
            cooling_enabled=False,
            forecasts=None,
        )

        assert result.output == 0.0
        assert result.status == "inactive"
        assert result.state.last_auto_output == 0.0
        assert result.state.last_update_iso == "2026-07-01T00:00:00+00:00"

    def test_valid_forecast_updates_charge_and_respects_step_limit(self) -> None:
        """Valid forecasts produce a bounded automatic output and updated state."""

        controller = CCAControllerStrategy()
        controller.restore_state(CCAState(charge_estimate=10.0, last_auto_output=5.0, last_heat_score=0.0, status="idle"))

        result = controller.compute(
            _resolved(
                cca_hot_day_threshold=26.0,
                cca_warm_night_threshold=18.0,
                cca_charge_gain=20.0,
                cca_discharge_gain=10.0,
                cca_charge_target_scale=100.0,
                cca_output_step_limit=4.0,
                cca_output_max=60.0,
            ),
            cooling_enabled=True,
            forecasts=[{"datetime": "2026-07-01T12:00:00+00:00", "temperature": 34.0, "templow": 24.0}],
        )

        assert result.heat_score is not None
        assert result.charge_target is not None
        assert result.charge_estimate > 0.0
        assert result.output == pytest.approx(9.0)
        assert result.status == "active"
        assert result.current_mode == "cooling"
