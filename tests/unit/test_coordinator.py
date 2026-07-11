"""Tests for coordinator.py.

Tests cover:
- Normal PI control cycle (heating, cooling, heat_cool).
- Enabled flag = False → PI pauses, CCA shuts down to 0.
- Auto-disable on HVAC off.
- Sensor faults (shutdown mode, hold mode with grace period).
- Target temperature modes (internal, external, climate).
- Runtime tuning changes (prop_band, int_time, output limits, update interval).
- restore_integral_term pass-through.

Uses a mock HA interface to isolate coordinator logic.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.components.climate.const import HVACAction, HVACMode
from homeassistant.core import HomeAssistant

from custom_components.pi_thermostat.cca_controller import CCAState
from custom_components.pi_thermostat.const import (
    CCA_COORDINATOR_POLL_INTERVAL_SECONDS,
    DOMAIN,
    SENSOR_FAULT_GRACE_PERIOD_SECONDS,
    UPDATE_INTERVAL_DEFAULT_SECONDS,
    CCAForecastUnavailableMode,
    ControlMode,
    OperatingMode,
    SensorFaultMode,
)
from custom_components.pi_thermostat.coordinator import DataUpdateCoordinator
from custom_components.pi_thermostat.data import CoordinatorData

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_entry(
    hass: HomeAssistant,
    options: dict[str, Any] | None = None,
) -> Any:
    """Create and add a MockConfigEntry with given options."""

    from pytest_homeassistant_custom_component.common import MockConfigEntry

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="PI Thermostat & CCA Control",
        data={},
        options=options or {},
    )
    entry.add_to_hass(hass)
    return entry


def _default_options(**overrides: Any) -> dict[str, Any]:
    """Return a minimal valid options dict with overrides."""

    base: dict[str, Any] = {
        "enabled": True,
        "operating_mode": OperatingMode.HEAT,
        "temp_sensor": "sensor.temperature",
        "target_temp_mode": "internal",
        "target_temp": 20.0,
    }
    base.update(overrides)
    return base


def _default_cca_options(**overrides: Any) -> dict[str, Any]:
    """Return a minimal valid CCA options dict with overrides."""

    base: dict[str, Any] = {
        "enabled": True,
        "control_mode": ControlMode.CCA,
        "cca_cooling_enable_entity": "binary_sensor.cooling_enabled",
        "cca_weather_entity": "weather.home",
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Test classes
# ---------------------------------------------------------------------------


class TestCoordinatorInit:
    """Test coordinator initialization."""

    async def test_creates_successfully(self, hass: HomeAssistant) -> None:
        """Coordinator initializes with default options."""

        entry = _make_entry(hass, _default_options())
        coordinator = DataUpdateCoordinator(hass, entry)

        assert coordinator is not None
        assert coordinator.update_interval == timedelta(seconds=UPDATE_INTERVAL_DEFAULT_SECONDS)

    async def test_custom_update_interval(self, hass: HomeAssistant) -> None:
        """Coordinator respects custom update interval."""

        entry = _make_entry(hass, _default_options(update_interval=30))
        coordinator = DataUpdateCoordinator(hass, entry)

        assert coordinator.update_interval == timedelta(seconds=30)

    async def test_restore_integral_term(self, hass: HomeAssistant) -> None:
        """restore_integral_term passes through to PI controller."""

        entry = _make_entry(hass, _default_options())
        coordinator = DataUpdateCoordinator(hass, entry)

        # Should not raise
        coordinator.restore_integral_term(42.5)
        assert coordinator._pi.get_integral_term() == pytest.approx(42.5, abs=0.1)

    async def test_restores_cca_state_from_storage(self, hass: HomeAssistant) -> None:
        """CCA mode restores persisted state from storage."""

        entry = _make_entry(hass, _default_cca_options())
        coordinator = DataUpdateCoordinator(hass, entry)

        with patch.object(
            coordinator._cca_store,
            "async_load",
            AsyncMock(
                return_value={
                    "charge_estimate": 12.5,
                    "last_auto_output": 8.0,
                    "last_heat_score": 55.0,
                    "last_update_iso": "2026-07-01T00:00:00+00:00",
                    "status": "active",
                }
            ),
        ):
            await coordinator.async_restore_cca_state()

        state = coordinator.get_cca_state()
        assert state.charge_estimate == 12.5
        assert state.last_auto_output == 8.0
        assert state.last_heat_score == 55.0
        assert state.last_update_iso == "2026-07-01T00:00:00+00:00"
        assert state.status == "active"


class TestNormalCycle:
    """Test a normal PI control cycle."""

    async def test_heating_cycle(self, hass: HomeAssistant) -> None:
        """Normal heating cycle returns valid CoordinatorData."""

        entry = _make_entry(
            hass,
            _default_options(
                operating_mode=OperatingMode.HEAT,
                target_temp=22.0,
            ),
        )
        coordinator = DataUpdateCoordinator(hass, entry)

        # Mock HA interface
        with patch.object(coordinator._ha, "get_temperature", return_value=20.0):
            data = await coordinator._async_update_data()

        assert isinstance(data, CoordinatorData)
        assert data.current_temp == 20.0
        assert data.target_temp == 22.0
        assert data.sensor_available is True
        assert data.current_mode == "heating"
        assert data.output >= 0.0  # Should be positive (needs heating)
        assert data.deviation == pytest.approx(2.0)  # 22 - 20

    async def test_cooling_cycle(self, hass: HomeAssistant) -> None:
        """Normal cooling cycle returns valid CoordinatorData."""

        entry = _make_entry(
            hass,
            _default_options(
                operating_mode=OperatingMode.COOL,
                target_temp=20.0,
            ),
        )
        coordinator = DataUpdateCoordinator(hass, entry)

        with patch.object(coordinator._ha, "get_temperature", return_value=22.0):
            data = await coordinator._async_update_data()

        assert data.current_temp == 22.0
        assert data.target_temp == 20.0
        assert data.current_mode == "cooling"
        assert data.output >= 0.0  # Should be positive (needs cooling)

    async def test_at_target_temp(self, hass: HomeAssistant) -> None:
        """At target temperature, output is near zero."""

        entry = _make_entry(hass, _default_options(target_temp=20.0))
        coordinator = DataUpdateCoordinator(hass, entry)

        with patch.object(coordinator._ha, "get_temperature", return_value=20.0):
            data = await coordinator._async_update_data()

        assert data.deviation == pytest.approx(0.0)

    async def test_stores_last_data(self, hass: HomeAssistant) -> None:
        """Coordinator stores result in _last_data after each cycle."""

        entry = _make_entry(hass, _default_options(target_temp=22.0))
        coordinator = DataUpdateCoordinator(hass, entry)

        assert coordinator._last_data is None

        with patch.object(coordinator._ha, "get_temperature", return_value=20.0):
            data = await coordinator._async_update_data()

        assert coordinator._last_data is data


class TestCCACycle:
    """Test the CCA control path."""

    async def test_cca_update_interval(self, hass: HomeAssistant) -> None:
        """CCA mode uses the fixed heartbeat poll interval."""

        entry = _make_entry(hass, _default_cca_options(cca_update_interval_minutes=360))
        coordinator = DataUpdateCoordinator(hass, entry)

        assert coordinator.update_interval == timedelta(seconds=CCA_COORDINATOR_POLL_INTERVAL_SECONDS)

    async def test_cca_disabled_cooling_returns_off(self, hass: HomeAssistant) -> None:
        """CCA returns 0 output while cooling is not permitted."""

        entry = _make_entry(hass, _default_cca_options())
        coordinator = DataUpdateCoordinator(hass, entry)

        with patch.object(coordinator._ha, "get_entity_on_state", return_value=False):
            data = await coordinator._async_update_data()

        assert data.output == 0.0
        assert data.current_mode == "off"
        assert data.cca_status == "inactive"

    async def test_cca_inverted_cooling_enable_allows_cooling_when_entity_is_off(self, hass: HomeAssistant) -> None:
        """CCA can interpret an off-state as cooling enabled when configured."""

        entry = _make_entry(hass, _default_cca_options(cca_cooling_enable_on=False))
        coordinator = DataUpdateCoordinator(hass, entry)

        with (
            patch.object(coordinator._ha, "get_entity_on_state", return_value=False),
            patch.object(
                coordinator._ha,
                "async_get_daily_forecasts",
                AsyncMock(return_value=[{"datetime": "2026-07-01T12:00:00+00:00", "temperature": 35.0, "templow": 24.0}]),
            ),
        ):
            data = await coordinator._async_update_data()

        assert data.output > 0.0
        assert data.current_mode == "cooling"
        assert data.cca_status == "active"

    async def test_cca_inverted_cooling_enable_stays_off_when_entity_is_unavailable(self, hass: HomeAssistant) -> None:
        """CCA does not treat an unreadable gate signal as cooling enabled."""

        entry = _make_entry(hass, _default_cca_options(cca_cooling_enable_on=False))
        coordinator = DataUpdateCoordinator(hass, entry)

        with patch.object(coordinator._ha, "get_entity_on_state", return_value=None):
            data = await coordinator._async_update_data()

        assert data.output == 0.0
        assert data.current_mode == "off"
        assert data.cca_status == "inactive"

    async def test_cca_unreadable_gate_preserves_restored_active_state(self, hass: HomeAssistant) -> None:
        """A transiently unreadable cooling gate preserves the restored active CCA state once."""

        entry = _make_entry(hass, _default_cca_options(cca_update_interval_minutes=360))
        coordinator = DataUpdateCoordinator(hass, entry)
        coordinator.restore_cca_state(
            CCAState(
                charge_estimate=18.0,
                last_auto_output=12.0,
                last_heat_score=45.0,
                last_update_iso=(datetime.now(UTC) - timedelta(hours=2)).isoformat(),
                status="active",
            )
        )

        with patch.object(coordinator._ha, "get_entity_on_state", return_value=None):
            data = await coordinator._async_update_data()

        assert data.output == 12.0
        assert data.current_mode == "cooling"
        assert data.cca_status == "active"
        assert data.cca_next_update_in == 240

        with patch.object(coordinator._ha, "get_entity_on_state", return_value=None):
            second_data = await coordinator._async_update_data()

        assert second_data.output == 0.0
        assert second_data.current_mode == "off"
        assert second_data.cca_status == "inactive"
        assert second_data.cca_next_update_in is None

    async def test_cca_gate_recovery_recomputes_immediately(self, hass: HomeAssistant) -> None:
        """When the cooling gate becomes readable/on again, CCA recovers immediately without waiting for the interval."""

        entry = _make_entry(hass, _default_cca_options(cca_update_interval_minutes=360))
        coordinator = DataUpdateCoordinator(hass, entry)
        coordinator.restore_cca_state(
            CCAState(
                charge_estimate=18.0,
                last_auto_output=12.0,
                last_heat_score=45.0,
                last_update_iso=(datetime.now(UTC) - timedelta(hours=2)).isoformat(),
                status="active",
            )
        )

        with patch.object(coordinator._ha, "get_entity_on_state", return_value=False):
            first_data = await coordinator._async_update_data()

        assert first_data.output == 0.0
        assert first_data.current_mode == "off"
        assert first_data.cca_status == "inactive"

        with (
            patch.object(coordinator._ha, "get_entity_on_state", return_value=True),
            patch.object(
                coordinator._ha,
                "async_get_daily_forecasts",
                AsyncMock(return_value=[{"datetime": "2026-07-01T12:00:00+00:00", "temperature": 35.0, "templow": 24.0}]),
            ) as mock_forecasts,
        ):
            second_data = await coordinator._async_update_data()

        assert second_data.output > 0.0
        assert second_data.current_mode == "cooling"
        assert second_data.cca_status == "active"
        assert second_data.cca_next_update_in == 360
        mock_forecasts.assert_awaited_once()

    async def test_cca_manual_override_replaces_auto_output(self, hass: HomeAssistant) -> None:
        """CCA manual override replaces the automatic output value."""

        entry = _make_entry(
            hass,
            _default_cca_options(
                cca_manual_override_enabled=True,
                cca_manual_output=42.0,
            ),
        )
        coordinator = DataUpdateCoordinator(hass, entry)

        with (
            patch.object(coordinator._ha, "get_entity_on_state", return_value=True),
            patch.object(
                coordinator._ha,
                "async_get_daily_forecasts",
                AsyncMock(return_value=[{"datetime": "2026-07-01T12:00:00+00:00", "temperature": 32.0, "templow": 22.0}]),
            ),
        ):
            data = await coordinator._async_update_data()

        assert data.output == 42.0
        assert data.current_mode == "cooling"
        assert data.cca_override_active == "on"
        assert data.cca_status == "manual_override"

    async def test_cca_forecast_hold_keeps_last_auto_output(self, hass: HomeAssistant) -> None:
        """CCA hold mode keeps the last automatic output when forecast retrieval fails."""

        entry = _make_entry(
            hass,
            _default_cca_options(
                cca_forecast_unavailable_mode=CCAForecastUnavailableMode.HOLD,
                cca_charge_target_scale=200.0,
            ),
        )
        coordinator = DataUpdateCoordinator(hass, entry)

        with (
            patch.object(coordinator._ha, "get_entity_on_state", return_value=True),
            patch.object(
                coordinator._ha,
                "async_get_daily_forecasts",
                AsyncMock(return_value=[{"datetime": "2026-07-01T12:00:00+00:00", "temperature": 35.0, "templow": 24.0}]),
            ),
        ):
            first_data = await coordinator._async_update_data()

        assert first_data.output > 0.0

        coordinator.restore_cca_state(
            coordinator.get_cca_state().__class__(
                charge_estimate=coordinator.get_cca_state().charge_estimate,
                last_auto_output=coordinator.get_cca_state().last_auto_output,
                last_heat_score=coordinator.get_cca_state().last_heat_score,
                last_update_iso=(datetime.now(UTC) - timedelta(hours=7)).isoformat(),
                status=coordinator.get_cca_state().status,
            )
        )

        with (
            patch.object(coordinator._ha, "get_entity_on_state", return_value=True),
            patch.object(
                coordinator._ha,
                "async_get_daily_forecasts",
                AsyncMock(side_effect=RuntimeError("forecast down")),
            ),
        ):
            second_data = await coordinator._async_update_data()

        assert second_data.output == first_data.output
        assert second_data.cca_status == "forecast_hold"

    async def test_cca_runtime_refresh_preserves_current_step(self, hass: HomeAssistant) -> None:
        """A runtime CCA tuning change refreshes state without consuming the next step."""

        entry = _make_entry(
            hass,
            _default_cca_options(
                cca_charge_target_scale=200.0,
                cca_output_step_limit=10.0,
                cca_update_interval_minutes=360,
            ),
        )
        coordinator = DataUpdateCoordinator(hass, entry)

        with (
            patch.object(coordinator._ha, "get_entity_on_state", return_value=True),
            patch.object(
                coordinator._ha,
                "async_get_daily_forecasts",
                AsyncMock(return_value=[{"datetime": "2026-07-01T12:00:00+00:00", "temperature": 35.0, "templow": 24.0}]),
            ),
        ):
            first_data = await coordinator._async_update_data()

        assert first_data.output == pytest.approx(10.0)

        hass.config_entries.async_update_entry(
            entry,
            options={
                **entry.options,
                "cca_output_step_limit": 20.0,
            },
        )

        with (
            patch.object(coordinator._ha, "get_entity_on_state", return_value=True),
            patch.object(
                coordinator._ha,
                "async_get_daily_forecasts",
                AsyncMock(return_value=[{"datetime": "2026-07-01T12:00:00+00:00", "temperature": 35.0, "templow": 24.0}]),
            ) as mock_forecasts,
        ):
            await coordinator.async_request_cca_runtime_recompute()

        second_data = coordinator._last_data

        assert second_data is not None
        assert second_data.output == pytest.approx(10.0)
        assert second_data.cca_status == "active"
        assert second_data.cca_next_update_in == 360
        mock_forecasts.assert_not_awaited()

    async def test_cca_interval_change_recomputes_when_now_due(self, hass: HomeAssistant) -> None:
        """A shorter runtime interval recomputes immediately once the elapsed time is due."""

        entry = _make_entry(
            hass,
            _default_cca_options(
                cca_charge_target_scale=200.0,
                cca_update_interval_minutes=360,
            ),
        )
        coordinator = DataUpdateCoordinator(hass, entry)
        coordinator.restore_cca_state(
            CCAState(
                charge_estimate=18.0,
                last_auto_output=12.0,
                last_heat_score=45.0,
                last_update_iso=(datetime.now(UTC) - timedelta(minutes=300)).isoformat(),
                status="active",
            )
        )

        hass.config_entries.async_update_entry(
            entry,
            options={
                **entry.options,
                "cca_update_interval_minutes": 240,
            },
        )

        with (
            patch.object(coordinator._ha, "get_entity_on_state", return_value=True),
            patch.object(
                coordinator._ha,
                "async_get_daily_forecasts",
                AsyncMock(return_value=[{"datetime": "2026-07-01T12:00:00+00:00", "temperature": 35.0, "templow": 24.0}]),
            ) as mock_forecasts,
        ):
            await coordinator.async_request_cca_runtime_recompute()

        refresh_data = coordinator._last_data

        assert refresh_data is not None
        assert refresh_data.output > 0.0
        assert refresh_data.cca_next_update_in == 240
        mock_forecasts.assert_awaited_once()

    async def test_cca_manual_override_applies_immediately(self, hass: HomeAssistant) -> None:
        """Manual override takes effect immediately without consuming a scheduled step."""

        entry = _make_entry(
            hass,
            _default_cca_options(
                cca_charge_target_scale=200.0,
                cca_output_step_limit=10.0,
                cca_update_interval_minutes=360,
            ),
        )
        coordinator = DataUpdateCoordinator(hass, entry)

        with (
            patch.object(coordinator._ha, "get_entity_on_state", return_value=True),
            patch.object(
                coordinator._ha,
                "async_get_daily_forecasts",
                AsyncMock(return_value=[{"datetime": "2026-07-01T12:00:00+00:00", "temperature": 35.0, "templow": 24.0}]),
            ),
        ):
            first_data = await coordinator._async_update_data()

        assert first_data.output == pytest.approx(10.0)

        hass.config_entries.async_update_entry(
            entry,
            options={
                **entry.options,
                "cca_manual_override_enabled": True,
                "cca_manual_output": 42.0,
            },
        )

        with (
            patch.object(coordinator._ha, "get_entity_on_state", return_value=True),
            patch.object(
                coordinator._ha,
                "async_get_daily_forecasts",
                AsyncMock(return_value=[{"datetime": "2026-07-01T12:00:00+00:00", "temperature": 35.0, "templow": 24.0}]),
            ) as mock_forecasts,
        ):
            await coordinator.async_request_cca_runtime_recompute()

        second_data = coordinator._last_data

        assert second_data is not None
        assert second_data.output == 42.0
        assert second_data.cca_override_active == "on"
        assert second_data.cca_status == "manual_override"
        assert second_data.cca_next_update_in == 360
        mock_forecasts.assert_not_awaited()

    async def test_cca_manual_override_disable_refresh_clears_override(self, hass: HomeAssistant) -> None:
        """Disabling manual override mid-interval clears the cached override state immediately."""

        entry = _make_entry(
            hass,
            _default_cca_options(
                cca_charge_target_scale=200.0,
                cca_output_step_limit=10.0,
                cca_update_interval_minutes=360,
                cca_manual_override_enabled=True,
                cca_manual_output=42.0,
            ),
        )
        coordinator = DataUpdateCoordinator(hass, entry)

        with (
            patch.object(coordinator._ha, "get_entity_on_state", return_value=True),
            patch.object(
                coordinator._ha,
                "async_get_daily_forecasts",
                AsyncMock(return_value=[{"datetime": "2026-07-01T12:00:00+00:00", "temperature": 35.0, "templow": 24.0}]),
            ),
        ):
            first_data = await coordinator._async_update_data()

        assert first_data.output == pytest.approx(42.0)
        assert coordinator.get_cca_state().status == "manual_override"
        assert coordinator.get_cca_state().last_auto_output == pytest.approx(10.0)

        hass.config_entries.async_update_entry(
            entry,
            options={
                **entry.options,
                "cca_manual_override_enabled": False,
            },
        )

        with (
            patch.object(coordinator._ha, "get_entity_on_state", return_value=True),
            patch.object(coordinator._ha, "async_get_daily_forecasts", AsyncMock()) as mock_forecasts,
        ):
            await coordinator.async_request_cca_runtime_recompute()

        second_data = coordinator._last_data

        assert second_data is not None
        assert second_data.output == pytest.approx(10.0)
        assert second_data.cca_override_active == "off"
        assert second_data.cca_status == "active"
        assert second_data.cca_next_update_in == 360
        assert coordinator.get_cca_state().status == "active"
        mock_forecasts.assert_not_awaited()

    async def test_cca_output_max_change_does_not_consume_next_step(self, hass: HomeAssistant) -> None:
        """A runtime output-maximum change must not advance the automatic CCA step."""

        entry = _make_entry(
            hass,
            _default_cca_options(
                cca_charge_target_scale=200.0,
                cca_output_step_limit=10.0,
                cca_output_max=60.0,
                cca_update_interval_minutes=360,
            ),
        )
        coordinator = DataUpdateCoordinator(hass, entry)

        with (
            patch.object(coordinator._ha, "get_entity_on_state", return_value=True),
            patch.object(
                coordinator._ha,
                "async_get_daily_forecasts",
                AsyncMock(return_value=[{"datetime": "2026-07-01T12:00:00+00:00", "temperature": 35.0, "templow": 24.0}]),
            ),
        ):
            first_data = await coordinator._async_update_data()

        assert first_data.output == pytest.approx(10.0)

        hass.config_entries.async_update_entry(
            entry,
            options={
                **entry.options,
                "cca_output_max": 80.0,
            },
        )

        with (
            patch.object(coordinator._ha, "get_entity_on_state", return_value=True),
            patch.object(coordinator._ha, "async_get_daily_forecasts", AsyncMock()) as mock_forecasts,
        ):
            await coordinator.async_request_cca_runtime_recompute()

        second_data = coordinator._last_data

        assert second_data is not None
        assert second_data.output == pytest.approx(10.0)
        assert second_data.cca_next_update_in == 360
        mock_forecasts.assert_not_awaited()

    async def test_cca_output_max_lower_clamps_immediately(self, hass: HomeAssistant) -> None:
        """Lowering the output maximum clamps the cached automatic output immediately."""

        entry = _make_entry(
            hass,
            _default_cca_options(
                cca_output_min=0.0,
                cca_output_max=60.0,
                cca_update_interval_minutes=360,
            ),
        )
        coordinator = DataUpdateCoordinator(hass, entry)
        coordinator.restore_cca_state(
            CCAState(
                charge_estimate=18.0,
                last_auto_output=30.0,
                last_heat_score=45.0,
                last_update_iso=datetime.now(UTC).isoformat(),
                status="active",
            )
        )

        hass.config_entries.async_update_entry(
            entry,
            options={
                **entry.options,
                "cca_output_max": 20.0,
            },
        )

        with (
            patch.object(coordinator._ha, "get_entity_on_state", return_value=True),
            patch.object(coordinator._ha, "async_get_daily_forecasts", AsyncMock()) as mock_forecasts,
        ):
            await coordinator.async_request_cca_runtime_recompute()

        second_data = coordinator._last_data

        assert second_data is not None
        assert second_data.output == pytest.approx(20.0)
        assert second_data.cca_status == "active"
        assert second_data.cca_next_update_in == 360
        assert coordinator.get_cca_state().last_auto_output == pytest.approx(20.0)
        mock_forecasts.assert_not_awaited()

    async def test_cca_output_min_raise_clamps_immediately(self, hass: HomeAssistant) -> None:
        """Raising the output minimum clamps the cached automatic output immediately."""

        entry = _make_entry(
            hass,
            _default_cca_options(
                cca_output_min=0.0,
                cca_output_max=60.0,
                cca_update_interval_minutes=360,
            ),
        )
        coordinator = DataUpdateCoordinator(hass, entry)
        coordinator.restore_cca_state(
            CCAState(
                charge_estimate=18.0,
                last_auto_output=10.0,
                last_heat_score=45.0,
                last_update_iso=datetime.now(UTC).isoformat(),
                status="active",
            )
        )

        hass.config_entries.async_update_entry(
            entry,
            options={
                **entry.options,
                "cca_output_min": 15.0,
            },
        )

        with (
            patch.object(coordinator._ha, "get_entity_on_state", return_value=True),
            patch.object(coordinator._ha, "async_get_daily_forecasts", AsyncMock()) as mock_forecasts,
        ):
            await coordinator.async_request_cca_runtime_recompute()

        second_data = coordinator._last_data

        assert second_data is not None
        assert second_data.output == pytest.approx(15.0)
        assert second_data.cca_status == "active"
        assert second_data.cca_next_update_in == 360
        assert coordinator.get_cca_state().last_auto_output == pytest.approx(15.0)
        mock_forecasts.assert_not_awaited()

    async def test_cca_reenable_refresh_recomputes_immediately(self, hass: HomeAssistant) -> None:
        """Re-enabling a CCA instance runs a real control step immediately."""

        entry = _make_entry(
            hass,
            _default_cca_options(
                enabled=False,
                cca_charge_target_scale=200.0,
                cca_update_interval_minutes=360,
            ),
        )
        coordinator = DataUpdateCoordinator(hass, entry)

        with patch.object(coordinator._ha, "get_entity_on_state", return_value=False):
            disabled_data = await coordinator._async_update_data()

        assert disabled_data.output == 0.0
        assert disabled_data.cca_status == "inactive"

        hass.config_entries.async_update_entry(
            entry,
            options={
                **entry.options,
                "enabled": True,
            },
        )

        with (
            patch.object(coordinator._ha, "get_entity_on_state", return_value=True),
            patch.object(
                coordinator._ha,
                "async_get_daily_forecasts",
                AsyncMock(return_value=[{"datetime": "2026-07-01T12:00:00+00:00", "temperature": 35.0, "templow": 24.0}]),
            ) as mock_forecasts,
        ):
            await coordinator.async_request_cca_runtime_recompute()

        data = coordinator._last_data

        assert data is not None
        assert data.output > 0.0
        assert data.current_mode == "cooling"
        assert data.cca_status == "active"
        assert data.cca_next_update_in == 360
        mock_forecasts.assert_awaited_once()

    async def test_cca_non_due_refresh_reports_time_until_next_update(self, hass: HomeAssistant) -> None:
        """Non-due CCA heartbeats expose the remaining countdown without fetching forecasts."""

        entry = _make_entry(hass, _default_cca_options(cca_update_interval_minutes=360))
        coordinator = DataUpdateCoordinator(hass, entry)
        coordinator.restore_cca_state(
            CCAState(
                charge_estimate=18.0,
                last_auto_output=12.0,
                last_heat_score=45.0,
                last_update_iso=(datetime.now(UTC) - timedelta(hours=2)).isoformat(),
                status="active",
            )
        )

        with (
            patch.object(coordinator._ha, "get_entity_on_state", return_value=True),
            patch.object(coordinator._ha, "async_get_daily_forecasts", AsyncMock()) as mock_forecasts,
        ):
            data = await coordinator._async_update_data()

        assert data.output == 12.0
        assert data.cca_status == "active"
        assert data.cca_next_update_in == 240
        mock_forecasts.assert_not_awaited()

    async def test_cca_overdue_refresh_recomputes_and_resets_countdown(self, hass: HomeAssistant) -> None:
        """Overdue CCA heartbeats perform a real control step immediately after restart."""

        entry = _make_entry(hass, _default_cca_options(cca_update_interval_minutes=360))
        coordinator = DataUpdateCoordinator(hass, entry)
        coordinator.restore_cca_state(
            CCAState(
                charge_estimate=18.0,
                last_auto_output=12.0,
                last_heat_score=45.0,
                last_update_iso=(datetime.now(UTC) - timedelta(hours=7)).isoformat(),
                status="active",
            )
        )

        with (
            patch.object(coordinator._ha, "get_entity_on_state", return_value=True),
            patch.object(
                coordinator._ha,
                "async_get_daily_forecasts",
                AsyncMock(return_value=[{"datetime": "2026-07-01T12:00:00+00:00", "temperature": 35.0, "templow": 24.0}]),
            ) as mock_forecasts,
        ):
            data = await coordinator._async_update_data()

        assert data.output > 0.0
        assert data.cca_status == "active"
        assert data.cca_next_update_in == 360
        mock_forecasts.assert_awaited_once()

    async def test_cca_inactive_state_hides_next_update_countdown(self, hass: HomeAssistant) -> None:
        """Inactive CCA results do not advertise a misleading update countdown."""

        entry = _make_entry(hass, _default_cca_options(cca_update_interval_minutes=360))
        coordinator = DataUpdateCoordinator(hass, entry)
        coordinator.restore_cca_state(
            CCAState(
                charge_estimate=18.0,
                last_auto_output=12.0,
                last_heat_score=45.0,
                last_update_iso=(datetime.now(UTC) - timedelta(hours=2)).isoformat(),
                status="active",
            )
        )

        with patch.object(coordinator._ha, "get_entity_on_state", return_value=False):
            data = await coordinator._async_update_data()

        assert data.output == 0.0
        assert data.current_mode == "off"
        assert data.cca_status == "inactive"
        assert data.cca_next_update_in is None

    async def test_cca_cycle_persists_state_to_storage(self, hass: HomeAssistant) -> None:
        """CCA mode persists the computed state after each update."""

        entry = _make_entry(hass, _default_cca_options())
        coordinator = DataUpdateCoordinator(hass, entry)

        with (
            patch.object(coordinator._ha, "get_entity_on_state", return_value=True),
            patch.object(
                coordinator._ha,
                "async_get_daily_forecasts",
                AsyncMock(return_value=[{"datetime": "2026-07-01T12:00:00+00:00", "temperature": 32.0, "templow": 22.0}]),
            ),
            patch.object(coordinator._cca_store, "async_save", AsyncMock()) as mock_save,
        ):
            await coordinator._async_update_data()

        mock_save.assert_awaited_once()
        saved_payload = mock_save.await_args.args[0]
        assert saved_payload["status"] == "active"
        assert "charge_estimate" in saved_payload
        assert "last_auto_output" in saved_payload


class TestPausedResult:
    """Test the enabled flag / pause behavior."""

    async def test_disabled_returns_paused(self, hass: HomeAssistant) -> None:
        """When enabled=False, returns paused result without running PI cycle."""

        entry = _make_entry(hass, _default_options(enabled=False))
        coordinator = DataUpdateCoordinator(hass, entry)

        data = await coordinator._async_update_data()

        assert isinstance(data, CoordinatorData)
        # No temp reading should have been attempted — output stays unknown
        assert data.output is None

    async def test_paused_preserves_last_state(self, hass: HomeAssistant) -> None:
        """Pausing after a cycle preserves the last output."""

        entry = _make_entry(hass, _default_options(enabled=True, target_temp=25.0))
        coordinator = DataUpdateCoordinator(hass, entry)

        # Run one normal cycle first
        with patch.object(coordinator._ha, "get_temperature", return_value=20.0):
            first_data = await coordinator._async_update_data()

        assert first_data.output > 0

        # Now disable — should preserve last output
        with patch.object(coordinator, "_resolve") as mock_resolve:
            from custom_components.pi_thermostat.config import resolve

            mock_resolve.return_value = resolve({"enabled": False})
            paused_data = await coordinator._async_update_data()

        assert paused_data.output == first_data.output
        assert paused_data.p_term == first_data.p_term
        assert paused_data.i_term == first_data.i_term

    async def test_paused_without_previous_data(self, hass: HomeAssistant) -> None:
        """Pausing without previous data returns unknown result (output=None)."""

        entry = _make_entry(hass, _default_options(enabled=False))
        coordinator = DataUpdateCoordinator(hass, entry)

        assert coordinator._last_data is None
        data = await coordinator._async_update_data()

        assert data.output is None

    async def test_disabled_cca_returns_shutdown_result(self, hass: HomeAssistant) -> None:
        """Disabling a CCA instance forces a persisted inactive zero-output state."""

        entry = _make_entry(hass, _default_cca_options(enabled=False))
        coordinator = DataUpdateCoordinator(hass, entry)

        data = await coordinator._async_update_data()

        assert data.output == 0.0
        assert data.current_mode == "off"
        assert data.cca_status == "inactive"
        assert data.cca_override_active == "off"
        assert coordinator._cca.get_state().last_auto_output == 0.0

    async def test_disabled_cca_resets_persisted_auto_output(self, hass: HomeAssistant) -> None:
        """Disabling after an active cycle clears the stored auto output to zero."""

        entry = _make_entry(hass, _default_cca_options())
        coordinator = DataUpdateCoordinator(hass, entry)

        with (
            patch.object(coordinator._ha, "get_entity_on_state", return_value=True),
            patch.object(
                coordinator._ha,
                "async_get_daily_forecasts",
                AsyncMock(return_value=[{"datetime": "2026-07-01T12:00:00+00:00", "temperature": 35.0, "templow": 24.0}]),
            ),
        ):
            first_data = await coordinator._async_update_data()

        assert first_data.output > 0.0
        assert coordinator._cca.get_state().last_auto_output > 0.0

        with patch.object(coordinator, "_resolve") as mock_resolve:
            from custom_components.pi_thermostat.config import resolve

            mock_resolve.return_value = resolve(_default_cca_options(enabled=False))
            disabled_data = await coordinator._async_update_data()

        assert disabled_data.output == 0.0
        assert disabled_data.cca_status == "inactive"
        assert coordinator._cca.get_state().last_auto_output == 0.0


class TestAutoDisable:
    """Test auto-disable on HVAC off."""

    async def test_auto_disable_on_hvac_off(self, hass: HomeAssistant) -> None:
        """Output is 0 when climate entity HVAC mode is off."""

        entry = _make_entry(
            hass,
            _default_options(
                climate_entity="climate.living_room",
                auto_disable_on_hvac_off=True,
                target_temp=22.0,
            ),
        )
        coordinator = DataUpdateCoordinator(hass, entry)

        with patch.object(coordinator._ha, "get_climate_hvac_mode", return_value=HVACMode.OFF):
            data = await coordinator._async_update_data()

        assert data.output == 0.0

    async def test_no_auto_disable_when_heating(self, hass: HomeAssistant) -> None:
        """Normal cycle when climate HVAC mode is heat."""

        entry = _make_entry(
            hass,
            _default_options(
                climate_entity="climate.living_room",
                auto_disable_on_hvac_off=True,
                target_temp=22.0,
            ),
        )
        coordinator = DataUpdateCoordinator(hass, entry)

        with (
            patch.object(coordinator._ha, "get_climate_hvac_mode", return_value=HVACMode.HEAT),
            patch.object(coordinator._ha, "get_temperature", return_value=20.0),
        ):
            data = await coordinator._async_update_data()

        assert data.current_temp == 20.0
        assert data.output >= 0.0

    async def test_auto_disable_off_setting(self, hass: HomeAssistant) -> None:
        """No auto-disable when the setting is disabled."""

        entry = _make_entry(
            hass,
            _default_options(
                climate_entity="climate.living_room",
                auto_disable_on_hvac_off=False,
                target_temp=22.0,
            ),
        )
        coordinator = DataUpdateCoordinator(hass, entry)

        with (
            patch.object(coordinator._ha, "get_climate_hvac_mode", return_value=HVACMode.OFF),
            patch.object(coordinator._ha, "get_temperature", return_value=20.0),
        ):
            data = await coordinator._async_update_data()

        # Should not be auto-disabled
        assert data.current_temp == 20.0


class TestSensorFault:
    """Test sensor fault handling."""

    async def test_shutdown_mode(self, hass: HomeAssistant) -> None:
        """Shutdown mode sets output to 0 when sensor is unavailable."""

        entry = _make_entry(
            hass,
            _default_options(
                sensor_fault_mode=SensorFaultMode.SHUTDOWN,
                target_temp=22.0,
            ),
        )
        coordinator = DataUpdateCoordinator(hass, entry)

        with patch.object(coordinator._ha, "get_temperature", return_value=None):
            data = await coordinator._async_update_data()

        assert data.output == 0.0
        assert data.sensor_available is False

    async def test_hold_mode_within_grace(self, hass: HomeAssistant) -> None:
        """Hold mode keeps last output within grace period."""

        entry = _make_entry(
            hass,
            _default_options(
                sensor_fault_mode=SensorFaultMode.HOLD,
                target_temp=25.0,
            ),
        )
        coordinator = DataUpdateCoordinator(hass, entry)

        # Run a normal cycle first to establish last_good_output
        with patch.object(coordinator._ha, "get_temperature", return_value=20.0):
            first_data = await coordinator._async_update_data()

        assert first_data.output > 0
        last_output = first_data.output

        # Now sensor goes unavailable — should hold
        with patch.object(coordinator._ha, "get_temperature", return_value=None):
            data = await coordinator._async_update_data()

        assert data.output == last_output
        assert data.sensor_available is False

    async def test_hold_mode_grace_exceeded(self, hass: HomeAssistant) -> None:
        """Hold mode shuts down after grace period exceeds."""

        entry = _make_entry(
            hass,
            _default_options(
                sensor_fault_mode=SensorFaultMode.HOLD,
                target_temp=25.0,
                update_interval=60,
            ),
        )
        coordinator = DataUpdateCoordinator(hass, entry)

        # Run a normal cycle first
        with patch.object(coordinator._ha, "get_temperature", return_value=20.0):
            await coordinator._async_update_data()

        # Calculate how many fault cycles until grace period exceeds
        grace_cycles = max(1, SENSOR_FAULT_GRACE_PERIOD_SECONDS // 60)

        # Run fault cycles up to grace period
        with patch.object(coordinator._ha, "get_temperature", return_value=None):
            for _ in range(grace_cycles):
                data = await coordinator._async_update_data()
                assert data.sensor_available is False

            # One more cycle — should shut down
            data = await coordinator._async_update_data()

        assert data.output == 0.0
        assert data.sensor_available is False

    async def test_hold_mode_no_prior_output_returns_unknown(self, hass: HomeAssistant) -> None:
        """Hold mode returns unknown result when no prior good output exists.

        On the first cycle after restart the sensor may be temporarily
        unavailable.  With no prior good output to hold, the coordinator
        must not emit output=0 (which would overwrite the entity's
        restored state and trigger a spurious bus write).  Instead it
        returns output=None so entity states remain unchanged.
        """

        entry = _make_entry(
            hass,
            _default_options(
                sensor_fault_mode=SensorFaultMode.HOLD,
                target_temp=25.0,
            ),
        )
        coordinator = DataUpdateCoordinator(hass, entry)

        # Sensor unavailable on the very first cycle — no prior output
        with patch.object(coordinator._ha, "get_temperature", return_value=None):
            data = await coordinator._async_update_data()

        assert data.output is None
        assert data.sensor_available is False

    async def test_fault_counter_resets_on_recovery(self, hass: HomeAssistant) -> None:
        """Fault counter resets when sensor recovers."""

        entry = _make_entry(
            hass,
            _default_options(
                sensor_fault_mode=SensorFaultMode.HOLD,
                target_temp=25.0,
            ),
        )
        coordinator = DataUpdateCoordinator(hass, entry)

        # Normal cycle
        with patch.object(coordinator._ha, "get_temperature", return_value=20.0):
            await coordinator._async_update_data()

        # Fault cycle
        with patch.object(coordinator._ha, "get_temperature", return_value=None):
            await coordinator._async_update_data()

        assert coordinator._fault_cycles == 1

        # Recovery
        with patch.object(coordinator._ha, "get_temperature", return_value=20.0):
            await coordinator._async_update_data()

        assert coordinator._fault_cycles == 0


class TestTargetTemp:
    """Test target temperature mode handling."""

    async def test_internal_target(self, hass: HomeAssistant) -> None:
        """Internal target mode uses configured target_temp."""

        entry = _make_entry(
            hass,
            _default_options(
                target_temp_mode="internal",
                target_temp=21.0,
            ),
        )
        coordinator = DataUpdateCoordinator(hass, entry)

        with patch.object(coordinator._ha, "get_temperature", return_value=20.0):
            data = await coordinator._async_update_data()

        assert data.target_temp == 21.0

    async def test_external_target(self, hass: HomeAssistant) -> None:
        """External target mode reads from target entity."""

        entry = _make_entry(
            hass,
            _default_options(
                target_temp_mode="external",
                target_temp_entity="input_number.setpoint",
            ),
        )
        coordinator = DataUpdateCoordinator(hass, entry)

        with (
            patch.object(coordinator._ha, "get_temperature", return_value=20.0),
            patch.object(coordinator._ha, "get_target_temperature", return_value=23.0),
        ):
            data = await coordinator._async_update_data()

        assert data.target_temp == 23.0

    async def test_external_target_unavailable_returns_unknown(self, hass: HomeAssistant) -> None:
        """External target mode follows HOLD behavior when target is unavailable."""

        entry = _make_entry(
            hass,
            _default_options(
                target_temp_mode="external",
                target_temp_entity="input_number.setpoint",
            ),
        )
        coordinator = DataUpdateCoordinator(hass, entry)

        with (
            patch.object(coordinator._ha, "get_temperature", return_value=20.0),
            patch.object(coordinator._ha, "get_target_temperature", return_value=None),
        ):
            data = await coordinator._async_update_data()

        assert data.current_temp == 20.0
        assert data.target_temp is None
        assert data.current_mode is None
        assert data.output is None
        assert data.sensor_available is True

    async def test_external_target_unavailable_shutdown_mode(self, hass: HomeAssistant) -> None:
        """External target mode uses shutdown behavior when configured."""

        entry = _make_entry(
            hass,
            _default_options(
                target_temp_mode="external",
                target_temp_entity="input_number.setpoint",
                sensor_fault_mode=SensorFaultMode.SHUTDOWN,
            ),
        )
        coordinator = DataUpdateCoordinator(hass, entry)

        with (
            patch.object(coordinator._ha, "get_temperature", return_value=20.0),
            patch.object(coordinator._ha, "get_target_temperature", return_value=None),
        ):
            data = await coordinator._async_update_data()

        assert data.current_temp == 20.0
        assert data.target_temp is None
        assert data.current_mode == "off"
        assert data.output == 0.0
        assert data.sensor_available is True

    async def test_climate_target(self, hass: HomeAssistant) -> None:
        """Climate target mode reads from climate entity's setpoint."""

        entry = _make_entry(
            hass,
            _default_options(
                target_temp_mode="climate",
                climate_entity="climate.living_room",
                operating_mode=OperatingMode.HEAT,
                auto_disable_on_hvac_off=False,
            ),
        )
        coordinator = DataUpdateCoordinator(hass, entry)

        with (
            patch.object(coordinator._ha, "get_temperature", return_value=20.0),
            patch.object(coordinator._ha, "get_climate_target_temperature", return_value=24.0),
            patch.object(coordinator._ha, "get_climate_hvac_action", return_value=HVACAction.HEATING),
        ):
            data = await coordinator._async_update_data()

        assert data.target_temp == 24.0

    async def test_climate_target_unavailable_returns_unknown(self, hass: HomeAssistant) -> None:
        """Climate target mode follows HOLD behavior when target is unavailable."""

        entry = _make_entry(
            hass,
            _default_options(
                target_temp_mode="climate",
                climate_entity="climate.living_room",
                operating_mode=OperatingMode.HEAT,
                auto_disable_on_hvac_off=False,
            ),
        )
        coordinator = DataUpdateCoordinator(hass, entry)

        with (
            patch.object(coordinator._ha, "get_temperature", return_value=20.0),
            patch.object(coordinator._ha, "get_climate_target_temperature", return_value=None),
            patch.object(coordinator._ha, "get_climate_hvac_action", return_value=HVACAction.HEATING),
        ):
            data = await coordinator._async_update_data()

        assert data.current_temp == 20.0
        assert data.target_temp is None
        assert data.current_mode is None
        assert data.output is None
        assert data.sensor_available is True


class TestDetermineCooling:
    """Test heating/cooling direction determination."""

    async def test_heat_mode_always_heating(self, hass: HomeAssistant) -> None:
        """Heat mode always uses heating direction."""

        entry = _make_entry(hass, _default_options(operating_mode=OperatingMode.HEAT))
        coordinator = DataUpdateCoordinator(hass, entry)

        from custom_components.pi_thermostat.config import resolve

        resolved = resolve(_default_options(operating_mode=OperatingMode.HEAT))
        assert coordinator._determine_cooling(resolved) is False

    async def test_cool_mode_always_cooling(self, hass: HomeAssistant) -> None:
        """Cool mode always uses cooling direction."""

        entry = _make_entry(hass, _default_options(operating_mode=OperatingMode.COOL))
        coordinator = DataUpdateCoordinator(hass, entry)

        from custom_components.pi_thermostat.config import resolve

        resolved = resolve(_default_options(operating_mode=OperatingMode.COOL))
        assert coordinator._determine_cooling(resolved) is True

    async def test_heat_cool_reads_climate_action(self, hass: HomeAssistant) -> None:
        """Heat+cool mode reads climate entity hvac_action."""

        entry = _make_entry(
            hass,
            _default_options(
                operating_mode=OperatingMode.HEAT_COOL,
                climate_entity="climate.room",
            ),
        )
        coordinator = DataUpdateCoordinator(hass, entry)

        from custom_components.pi_thermostat.config import resolve

        resolved = resolve(
            _default_options(
                operating_mode=OperatingMode.HEAT_COOL,
                climate_entity="climate.room",
            )
        )

        with patch.object(coordinator._ha, "get_climate_hvac_action", return_value=HVACAction.COOLING):
            assert coordinator._determine_cooling(resolved) is True

        with patch.object(coordinator._ha, "get_climate_hvac_action", return_value=HVACAction.HEATING):
            assert coordinator._determine_cooling(resolved) is False

    async def test_heat_cool_defaults_to_heating(self, hass: HomeAssistant) -> None:
        """Heat+cool defaults to heating when action and mode are unknown."""

        entry = _make_entry(
            hass,
            _default_options(
                operating_mode=OperatingMode.HEAT_COOL,
                climate_entity="climate.room",
            ),
        )
        coordinator = DataUpdateCoordinator(hass, entry)

        from custom_components.pi_thermostat.config import resolve

        resolved = resolve(
            _default_options(
                operating_mode=OperatingMode.HEAT_COOL,
                climate_entity="climate.room",
            )
        )

        with (
            patch.object(coordinator._ha, "get_climate_hvac_action", return_value=None),
            patch.object(coordinator._ha, "get_climate_hvac_mode", return_value=None),
        ):
            assert coordinator._determine_cooling(resolved) is False

    async def test_heat_cool_uses_hvac_mode_when_action_is_idle(self, hass: HomeAssistant) -> None:
        """Heat+cool uses climate mode when hvac_action is idle."""

        entry = _make_entry(
            hass,
            _default_options(
                operating_mode=OperatingMode.HEAT_COOL,
                climate_entity="climate.room",
            ),
        )
        coordinator = DataUpdateCoordinator(hass, entry)

        from custom_components.pi_thermostat.config import resolve

        resolved = resolve(
            _default_options(
                operating_mode=OperatingMode.HEAT_COOL,
                climate_entity="climate.room",
            )
        )

        with (
            patch.object(coordinator._ha, "get_climate_hvac_action", return_value=HVACAction.IDLE),
            patch.object(coordinator._ha, "get_climate_hvac_mode", return_value=HVACMode.COOL),
        ):
            assert coordinator._determine_cooling(resolved) is True


class TestTuningChanges:
    """Test runtime tuning change detection and application."""

    async def test_prop_band_change(self, hass: HomeAssistant) -> None:
        """Changing proportional band updates the PI controller."""

        entry = _make_entry(hass, _default_options(proportional_band=4.0))
        coordinator = DataUpdateCoordinator(hass, entry)

        assert coordinator._last_prop_band == 4.0

        from custom_components.pi_thermostat.config import resolve

        resolved = resolve(_default_options(proportional_band=8.0))
        coordinator._apply_tuning_changes(resolved)

        assert coordinator._last_prop_band == 8.0

    async def test_int_time_change(self, hass: HomeAssistant) -> None:
        """Changing integral time updates the PI controller."""

        entry = _make_entry(hass, _default_options(integral_time=30.0))
        coordinator = DataUpdateCoordinator(hass, entry)

        from custom_components.pi_thermostat.config import resolve

        resolved = resolve(_default_options(integral_time=60.0))
        coordinator._apply_tuning_changes(resolved)

        assert coordinator._last_int_time == 60.0

    async def test_output_limits_change(self, hass: HomeAssistant) -> None:
        """Changing output limits updates the PI controller."""

        entry = _make_entry(hass, _default_options(output_min=0.0, output_max=100.0))
        coordinator = DataUpdateCoordinator(hass, entry)

        from custom_components.pi_thermostat.config import resolve

        resolved = resolve(_default_options(output_min=10.0, output_max=90.0))
        coordinator._apply_tuning_changes(resolved)

        assert coordinator._last_output_min == 10.0
        assert coordinator._last_output_max == 90.0

    async def test_update_interval_change(self, hass: HomeAssistant) -> None:
        """Changing update interval updates both PI controller and coordinator."""

        entry = _make_entry(hass, _default_options(update_interval=60))
        coordinator = DataUpdateCoordinator(hass, entry)

        from custom_components.pi_thermostat.config import resolve

        resolved = resolve(_default_options(update_interval=30))
        coordinator._apply_tuning_changes(resolved)

        assert coordinator._last_update_interval == 30
        assert coordinator.update_interval == timedelta(seconds=30)

    async def test_no_change_no_update(self, hass: HomeAssistant) -> None:
        """No tuning update when values haven't changed."""

        entry = _make_entry(hass, _default_options())
        coordinator = DataUpdateCoordinator(hass, entry)

        from custom_components.pi_thermostat.config import resolve

        original_prop_band = coordinator._last_prop_band
        resolved = resolve(_default_options())
        coordinator._apply_tuning_changes(resolved)

        assert coordinator._last_prop_band == original_prop_band


class TestTempSensorSources:
    """Test current temperature source selection."""

    async def test_dedicated_sensor_preferred(self, hass: HomeAssistant) -> None:
        """Dedicated temp sensor is preferred over climate entity."""

        entry = _make_entry(
            hass,
            _default_options(
                temp_sensor="sensor.temperature",
                climate_entity="climate.room",
                operating_mode=OperatingMode.HEAT,
                auto_disable_on_hvac_off=False,
            ),
        )
        coordinator = DataUpdateCoordinator(hass, entry)

        from custom_components.pi_thermostat.config import resolve

        resolved = resolve(
            _default_options(
                temp_sensor="sensor.temperature",
                climate_entity="climate.room",
            )
        )

        with (
            patch.object(coordinator._ha, "get_temperature", return_value=21.0) as mock_sensor,
            patch.object(coordinator._ha, "get_climate_current_temperature") as mock_climate,
        ):
            result = coordinator._read_current_temp(resolved)

        mock_sensor.assert_called_once_with("sensor.temperature")
        mock_climate.assert_not_called()
        assert result == 21.0

    async def test_climate_fallback(self, hass: HomeAssistant) -> None:
        """Climate entity's current_temperature is used when no sensor."""

        entry = _make_entry(
            hass,
            _default_options(
                temp_sensor="",
                climate_entity="climate.room",
            ),
        )
        coordinator = DataUpdateCoordinator(hass, entry)

        from custom_components.pi_thermostat.config import resolve

        resolved = resolve(
            _default_options(
                temp_sensor="",
                climate_entity="climate.room",
            )
        )

        with patch.object(coordinator._ha, "get_climate_current_temperature", return_value=19.5):
            result = coordinator._read_current_temp(resolved)

        assert result == 19.5
