"""Tests for coordinator.py.

Tests cover:
- Normal PI control cycle (heating, cooling, heat_cool).
- Enabled flag = False → paused result (preserves last state).
- Auto-disable on HVAC off.
- Sensor faults (shutdown mode, hold mode with grace period).
- Target temperature modes (internal, external, climate).
- Runtime tuning changes (prop_band, int_time, output limits, update interval).
- restore_integral_term pass-through.

Uses a mock HA interface to isolate coordinator logic.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.components.climate.const import HVACAction, HVACMode
from homeassistant.core import HomeAssistant

from custom_components.pi_thermostat.const import (
    DOMAIN,
    SENSOR_FAULT_GRACE_PERIOD_SECONDS,
    UPDATE_INTERVAL_DEFAULT_SECONDS,
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
        title="PI Thermostat",
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
        with (
            patch.object(coordinator._ha, "get_temperature", return_value=20.0),
            patch.object(coordinator._ha, "set_output", new_callable=AsyncMock),
        ):
            data = await coordinator._async_update_data()

        assert isinstance(data, CoordinatorData)
        assert data.current_temp == 20.0
        assert data.target_temp == 22.0
        assert data.sensor_available is True
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

        with (
            patch.object(coordinator._ha, "get_temperature", return_value=22.0),
            patch.object(coordinator._ha, "set_output", new_callable=AsyncMock),
        ):
            data = await coordinator._async_update_data()

        assert data.current_temp == 22.0
        assert data.target_temp == 20.0
        assert data.output >= 0.0  # Should be positive (needs cooling)

    async def test_at_target_temp(self, hass: HomeAssistant) -> None:
        """At target temperature, output is near zero."""

        entry = _make_entry(hass, _default_options(target_temp=20.0))
        coordinator = DataUpdateCoordinator(hass, entry)

        with (
            patch.object(coordinator._ha, "get_temperature", return_value=20.0),
            patch.object(coordinator._ha, "set_output", new_callable=AsyncMock),
        ):
            data = await coordinator._async_update_data()

        assert data.deviation == pytest.approx(0.0)

    async def test_output_written_to_entity(self, hass: HomeAssistant) -> None:
        """Output is written to the configured output entity."""

        entry = _make_entry(
            hass,
            _default_options(
                output_entity="input_number.output",
                target_temp=22.0,
            ),
        )
        coordinator = DataUpdateCoordinator(hass, entry)

        mock_set_output = AsyncMock()
        with (
            patch.object(coordinator._ha, "get_temperature", return_value=20.0),
            patch.object(coordinator._ha, "set_output", mock_set_output),
        ):
            data = await coordinator._async_update_data()

        mock_set_output.assert_called_once_with("input_number.output", data.output)

    async def test_output_write_failure_does_not_crash(self, hass: HomeAssistant) -> None:
        """Output write failure logs warning but doesn't crash."""

        entry = _make_entry(
            hass,
            _default_options(
                output_entity="input_number.output",
                target_temp=22.0,
            ),
        )
        coordinator = DataUpdateCoordinator(hass, entry)

        mock_set_output = AsyncMock(side_effect=Exception("service call failed"))
        with (
            patch.object(coordinator._ha, "get_temperature", return_value=20.0),
            patch.object(coordinator._ha, "set_output", mock_set_output),
        ):
            data = await coordinator._async_update_data()

        # Should still return data successfully
        assert isinstance(data, CoordinatorData)
        assert data.current_temp == 20.0

    async def test_stores_last_data(self, hass: HomeAssistant) -> None:
        """Coordinator stores result in _last_data after each cycle."""

        entry = _make_entry(hass, _default_options(target_temp=22.0))
        coordinator = DataUpdateCoordinator(hass, entry)

        assert coordinator._last_data is None

        with (
            patch.object(coordinator._ha, "get_temperature", return_value=20.0),
            patch.object(coordinator._ha, "set_output", new_callable=AsyncMock),
        ):
            data = await coordinator._async_update_data()

        assert coordinator._last_data is data


class TestPausedResult:
    """Test the enabled flag / pause behavior."""

    async def test_disabled_returns_paused(self, hass: HomeAssistant) -> None:
        """When enabled=False, returns paused result without running PI cycle."""

        entry = _make_entry(hass, _default_options(enabled=False))
        coordinator = DataUpdateCoordinator(hass, entry)

        data = await coordinator._async_update_data()

        assert isinstance(data, CoordinatorData)
        # No temp reading should have been attempted
        assert data.output == 0.0

    async def test_paused_preserves_last_state(self, hass: HomeAssistant) -> None:
        """Pausing after a cycle preserves the last output."""

        entry = _make_entry(hass, _default_options(enabled=True, target_temp=25.0))
        coordinator = DataUpdateCoordinator(hass, entry)

        # Run one normal cycle first
        with (
            patch.object(coordinator._ha, "get_temperature", return_value=20.0),
            patch.object(coordinator._ha, "set_output", new_callable=AsyncMock),
        ):
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
        """Pausing without previous data returns shutdown result."""

        entry = _make_entry(hass, _default_options(enabled=False))
        coordinator = DataUpdateCoordinator(hass, entry)

        assert coordinator._last_data is None
        data = await coordinator._async_update_data()

        assert data.output == 0.0


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

        with (
            patch.object(coordinator._ha, "get_climate_hvac_mode", return_value=HVACMode.OFF),
            patch.object(coordinator._ha, "set_output", new_callable=AsyncMock),
        ):
            data = await coordinator._async_update_data()

        assert data.output == 0.0

    async def test_auto_disable_writes_zero_to_output_entity(self, hass: HomeAssistant) -> None:
        """Auto-disable writes 0 to the output entity."""

        entry = _make_entry(
            hass,
            _default_options(
                climate_entity="climate.living_room",
                auto_disable_on_hvac_off=True,
                output_entity="input_number.output",
                target_temp=22.0,
            ),
        )
        coordinator = DataUpdateCoordinator(hass, entry)

        mock_set_output = AsyncMock()
        with (
            patch.object(coordinator._ha, "get_climate_hvac_mode", return_value=HVACMode.OFF),
            patch.object(coordinator._ha, "set_output", mock_set_output),
        ):
            await coordinator._async_update_data()

        mock_set_output.assert_called_once_with("input_number.output", 0.0)

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
            patch.object(coordinator._ha, "set_output", new_callable=AsyncMock),
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
            patch.object(coordinator._ha, "set_output", new_callable=AsyncMock),
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

        with (
            patch.object(coordinator._ha, "get_temperature", return_value=None),
            patch.object(coordinator._ha, "set_output", new_callable=AsyncMock),
        ):
            data = await coordinator._async_update_data()

        assert data.output == 0.0
        assert data.sensor_available is False

    async def test_shutdown_mode_writes_zero_to_output_entity(self, hass: HomeAssistant) -> None:
        """Shutdown mode writes 0 to the output entity."""

        entry = _make_entry(
            hass,
            _default_options(
                sensor_fault_mode=SensorFaultMode.SHUTDOWN,
                output_entity="input_number.output",
                target_temp=22.0,
            ),
        )
        coordinator = DataUpdateCoordinator(hass, entry)

        mock_set_output = AsyncMock()
        with (
            patch.object(coordinator._ha, "get_temperature", return_value=None),
            patch.object(coordinator._ha, "set_output", mock_set_output),
        ):
            await coordinator._async_update_data()

        mock_set_output.assert_called_once_with("input_number.output", 0.0)

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
        with (
            patch.object(coordinator._ha, "get_temperature", return_value=20.0),
            patch.object(coordinator._ha, "set_output", new_callable=AsyncMock),
        ):
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
        with (
            patch.object(coordinator._ha, "get_temperature", return_value=20.0),
            patch.object(coordinator._ha, "set_output", new_callable=AsyncMock),
        ):
            await coordinator._async_update_data()

        # Calculate how many fault cycles until grace period exceeds
        grace_cycles = max(1, SENSOR_FAULT_GRACE_PERIOD_SECONDS // 60)

        # Run fault cycles up to grace period
        with patch.object(coordinator._ha, "get_temperature", return_value=None):
            for _ in range(grace_cycles):
                data = await coordinator._async_update_data()
                assert data.sensor_available is False

            # One more cycle — should shut down
            with patch.object(coordinator._ha, "set_output", new_callable=AsyncMock):
                data = await coordinator._async_update_data()

        assert data.output == 0.0
        assert data.sensor_available is False

    async def test_hold_mode_grace_exceeded_writes_zero(self, hass: HomeAssistant) -> None:
        """Hold mode writes 0 to output entity when grace period exceeds."""

        entry = _make_entry(
            hass,
            _default_options(
                sensor_fault_mode=SensorFaultMode.HOLD,
                output_entity="input_number.output",
                target_temp=25.0,
                update_interval=60,
            ),
        )
        coordinator = DataUpdateCoordinator(hass, entry)

        # Run a normal cycle first
        with (
            patch.object(coordinator._ha, "get_temperature", return_value=20.0),
            patch.object(coordinator._ha, "set_output", new_callable=AsyncMock),
        ):
            await coordinator._async_update_data()

        grace_cycles = max(1, SENSOR_FAULT_GRACE_PERIOD_SECONDS // 60)

        with patch.object(coordinator._ha, "get_temperature", return_value=None):
            for _ in range(grace_cycles):
                await coordinator._async_update_data()

            mock_set_output = AsyncMock()
            with patch.object(coordinator._ha, "set_output", mock_set_output):
                await coordinator._async_update_data()

        mock_set_output.assert_called_once_with("input_number.output", 0.0)

    async def test_hold_mode_no_prior_output_shuts_down(self, hass: HomeAssistant) -> None:
        """Hold mode shuts down when no prior good output exists (e.g. first cycle after restart)."""

        entry = _make_entry(
            hass,
            _default_options(
                sensor_fault_mode=SensorFaultMode.HOLD,
                target_temp=25.0,
            ),
        )
        coordinator = DataUpdateCoordinator(hass, entry)

        # Sensor unavailable on the very first cycle — no prior output
        mock_set_output = AsyncMock()
        with (
            patch.object(coordinator._ha, "get_temperature", return_value=None),
            patch.object(coordinator._ha, "set_output", mock_set_output),
        ):
            data = await coordinator._async_update_data()

        assert data.output == 0.0
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
        with (
            patch.object(coordinator._ha, "get_temperature", return_value=20.0),
            patch.object(coordinator._ha, "set_output", new_callable=AsyncMock),
        ):
            await coordinator._async_update_data()

        # Fault cycle
        with patch.object(coordinator._ha, "get_temperature", return_value=None):
            await coordinator._async_update_data()

        assert coordinator._fault_cycles == 1

        # Recovery
        with (
            patch.object(coordinator._ha, "get_temperature", return_value=20.0),
            patch.object(coordinator._ha, "set_output", new_callable=AsyncMock),
        ):
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

        with (
            patch.object(coordinator._ha, "get_temperature", return_value=20.0),
            patch.object(coordinator._ha, "set_output", new_callable=AsyncMock),
        ):
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
            patch.object(coordinator._ha, "set_output", new_callable=AsyncMock),
        ):
            data = await coordinator._async_update_data()

        assert data.target_temp == 23.0

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
            patch.object(coordinator._ha, "set_output", new_callable=AsyncMock),
        ):
            data = await coordinator._async_update_data()

        assert data.target_temp == 24.0


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
        """Heat+cool defaults to heating when action is unknown."""

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

        with patch.object(coordinator._ha, "get_climate_hvac_action", return_value=None):
            assert coordinator._determine_cooling(resolved) is False


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
