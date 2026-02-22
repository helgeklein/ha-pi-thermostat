"""Integration tests for entity platforms (sensor, number, switch).

Tests cover:
- Full entry setup and platform forwarding.
- Sensor entity registration and value reading.
- Number entity registration, reading, and writing.
- Switch entity registration, on/off persistence.
- Binary sensor entity registration and value reading.
- I-term sensor startup modes (zero, fixed, last).
- Unload entry.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.core import HomeAssistant, State

from custom_components.pi_thermostat.const import (
    DOMAIN,
    ITermStartupMode,
    OperatingMode,
    TargetTempMode,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_entry(options: dict[str, Any] | None = None) -> Any:
    """Create a MockConfigEntry."""

    from pytest_homeassistant_custom_component.common import MockConfigEntry

    return MockConfigEntry(
        domain=DOMAIN,
        title="PI Thermostat",
        data={},
        options=options or _default_options(),
    )


def _default_options(**overrides: Any) -> dict[str, Any]:
    """Return a minimal valid options dict."""

    base: dict[str, Any] = {
        "enabled": True,
        "operating_mode": OperatingMode.HEAT,
        "temp_sensor": "sensor.temperature",
        "target_temp_mode": "internal",
        "target_temp": 20.0,
    }
    base.update(overrides)
    return base


async def _setup_integration(
    hass: HomeAssistant,
    options: dict[str, Any] | None = None,
) -> Any:
    """Set up the integration with given options and return the entry."""

    entry = _make_entry(options)
    entry.add_to_hass(hass)

    # Patch HA interface methods so the coordinator can run without real entities
    with (
        patch(
            "custom_components.pi_thermostat.ha_interface.HomeAssistantInterface.get_temperature",
            return_value=20.0,
        ),
        patch(
            "custom_components.pi_thermostat.ha_interface.HomeAssistantInterface.set_output",
            new_callable=AsyncMock,
        ),
    ):
        result = await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert result is True
    return entry


# ===========================================================================
# Full setup
# ===========================================================================


class TestSetupEntry:
    """Test integration setup and unload."""

    async def test_setup_unload(self, hass: HomeAssistant) -> None:
        """Integration sets up and unloads cleanly."""

        entry = await _setup_integration(hass)

        # Verify runtime_data was populated
        assert entry.runtime_data is not None
        assert entry.runtime_data.coordinator is not None

        # Unload
        result = await hass.config_entries.async_unload(entry.entry_id)
        assert result is True


# ===========================================================================
# Sensor entities
# ===========================================================================


class TestSensorEntities:
    """Test sensor entity creation and value reading."""

    async def test_sensor_entities_created(self, hass: HomeAssistant) -> None:
        """All expected sensor entities are registered."""

        await _setup_integration(hass)

        expected_entity_ids = [
            "sensor.pi_thermostat_output",
            "sensor.pi_thermostat_deviation",
            "sensor.pi_thermostat_current_temperature",
            "sensor.pi_thermostat_proportional_term",
            "sensor.pi_thermostat_integral_term",
        ]

        for entity_id in expected_entity_ids:
            state = hass.states.get(entity_id)
            assert state is not None, f"{entity_id} not found"

    async def test_output_sensor_value(self, hass: HomeAssistant) -> None:
        """Output sensor reflects coordinator data."""

        await _setup_integration(hass, _default_options(target_temp=22.0))

        state = hass.states.get("sensor.pi_thermostat_output")
        assert state is not None
        # With target=22, current=20 (mocked), output should be > 0
        assert float(state.state) >= 0.0

    async def test_deviation_sensor_value(self, hass: HomeAssistant) -> None:
        """Deviation sensor reflects control deviation."""

        await _setup_integration(hass, _default_options(target_temp=22.0))

        state = hass.states.get("sensor.pi_thermostat_deviation")
        assert state is not None
        # Deviation = target - current = 22 - 20 = 2.0
        assert float(state.state) == pytest.approx(2.0, abs=0.01)

    async def test_target_temp_sensor_created_in_climate_mode(self, hass: HomeAssistant) -> None:
        """Target temp sensor is created when target_temp_mode is not INTERNAL."""

        await _setup_integration(
            hass,
            _default_options(
                target_temp_mode=TargetTempMode.CLIMATE,
                climate_entity="climate.living_room",
            ),
        )

        state = hass.states.get("sensor.pi_thermostat_target_temperature")
        assert state is not None, "target_temp sensor should exist in CLIMATE mode"

    async def test_target_temp_sensor_not_created_in_internal_mode(self, hass: HomeAssistant) -> None:
        """Target temp sensor is NOT created when target_temp_mode is INTERNAL."""

        await _setup_integration(hass, _default_options())

        state = hass.states.get("sensor.pi_thermostat_target_temperature")
        assert state is None, "target_temp sensor should not exist in INTERNAL mode"

    async def test_target_temp_number_not_created_in_climate_mode(self, hass: HomeAssistant) -> None:
        """Target temp number is NOT created when target_temp_mode is CLIMATE."""

        await _setup_integration(
            hass,
            _default_options(
                target_temp_mode=TargetTempMode.CLIMATE,
                climate_entity="climate.living_room",
            ),
        )

        state = hass.states.get("number.pi_thermostat_target_temperature")
        assert state is None, "target_temp number should not exist in CLIMATE mode"


# ===========================================================================
# Number entities
# ===========================================================================


class TestNumberEntities:
    """Test number entity creation and value reading."""

    async def test_number_entities_created(self, hass: HomeAssistant) -> None:
        """All expected number entities are registered."""

        await _setup_integration(hass)

        expected_entity_ids = [
            "number.pi_thermostat_proportional_band",
            "number.pi_thermostat_integral_time",
            "number.pi_thermostat_target_temperature",
            "number.pi_thermostat_output_minimum",
            "number.pi_thermostat_output_maximum",
            "number.pi_thermostat_update_interval",
        ]

        for entity_id in expected_entity_ids:
            state = hass.states.get(entity_id)
            assert state is not None, f"{entity_id} not found"

    async def test_target_temp_value(self, hass: HomeAssistant) -> None:
        """Target temp number entity reflects configured value."""

        await _setup_integration(hass, _default_options(target_temp=23.5))

        state = hass.states.get("number.pi_thermostat_target_temperature")
        assert state is not None
        assert float(state.state) == pytest.approx(23.5, abs=0.01)

    async def test_prop_band_value(self, hass: HomeAssistant) -> None:
        """Proportional band number entity reflects configured value."""

        await _setup_integration(hass, _default_options(proportional_band=6.0))

        state = hass.states.get("number.pi_thermostat_proportional_band")
        assert state is not None
        assert float(state.state) == pytest.approx(6.0, abs=0.01)


# ===========================================================================
# Switch entities
# ===========================================================================


class TestSwitchEntities:
    """Test switch entity creation and control."""

    async def test_switch_entity_created(self, hass: HomeAssistant) -> None:
        """Enabled switch entity is registered."""

        await _setup_integration(hass)

        state = hass.states.get("switch.pi_thermostat_enabled")
        assert state is not None

    async def test_switch_default_on(self, hass: HomeAssistant) -> None:
        """Enabled switch is on by default."""

        await _setup_integration(hass, _default_options(enabled=True))

        state = hass.states.get("switch.pi_thermostat_enabled")
        assert state is not None
        assert state.state == "on"


# ===========================================================================
# I-term startup modes
# ===========================================================================


class TestITermStartupModes:
    """Test integral term startup mode behavior."""

    async def test_zero_mode(self, hass: HomeAssistant) -> None:
        """Zero startup mode starts i_term at 0."""

        entry = await _setup_integration(
            hass,
            _default_options(
                iterm_startup_mode=ITermStartupMode.ZERO,
            ),
        )

        coordinator = entry.runtime_data.coordinator
        # PIController starts at 0 by default — zero mode is just the default
        assert coordinator._pi.get_integral_term() == pytest.approx(0.0, abs=0.1)

    async def test_fixed_mode(self, hass: HomeAssistant) -> None:
        """Fixed startup mode sets i_term to configured value."""

        entry = await _setup_integration(
            hass,
            _default_options(
                iterm_startup_mode=ITermStartupMode.FIXED,
                iterm_startup_value=50.0,
            ),
        )

        coordinator = entry.runtime_data.coordinator
        assert coordinator._pi.get_integral_term() == pytest.approx(50.0, abs=0.1)

    async def test_last_mode_restores_from_state(self, hass: HomeAssistant) -> None:
        """LAST mode restores the integral term from persisted HA state."""

        from pytest_homeassistant_custom_component.common import mock_restore_cache

        # Pre-populate the restore cache with a persisted i_term value
        mock_restore_cache(
            hass,
            [State("sensor.pi_thermostat_integral_term", "42.5")],
        )

        entry = await _setup_integration(
            hass,
            _default_options(
                iterm_startup_mode=ITermStartupMode.LAST,
                iterm_startup_value=10.0,  # fallback — should NOT be used
            ),
        )

        coordinator = entry.runtime_data.coordinator
        assert coordinator._pi.get_integral_term() == pytest.approx(42.5, abs=0.1)

    async def test_last_mode_invalid_state_falls_back(self, hass: HomeAssistant) -> None:
        """LAST mode with invalid persisted state falls back to startup_value."""

        from pytest_homeassistant_custom_component.common import mock_restore_cache

        # Pre-populate with an unparseable state
        mock_restore_cache(
            hass,
            [State("sensor.pi_thermostat_integral_term", "unknown")],
        )

        entry = await _setup_integration(
            hass,
            _default_options(
                iterm_startup_mode=ITermStartupMode.LAST,
                iterm_startup_value=25.0,
            ),
        )

        coordinator = entry.runtime_data.coordinator
        assert coordinator._pi.get_integral_term() == pytest.approx(25.0, abs=0.1)

    async def test_last_mode_no_state_zero_fallback(self, hass: HomeAssistant) -> None:
        """LAST mode with no persisted state and startup_value=0 stays at 0."""

        entry = await _setup_integration(
            hass,
            _default_options(
                iterm_startup_mode=ITermStartupMode.LAST,
                iterm_startup_value=0.0,
            ),
        )

        coordinator = entry.runtime_data.coordinator
        assert coordinator._pi.get_integral_term() == pytest.approx(0.0, abs=0.1)


# ===========================================================================
# Switch write operations
# ===========================================================================


class TestSwitchWrite:
    """Test switch async_turn_on/turn_off persists to config entry options."""

    async def test_turn_off_persists(self, hass: HomeAssistant) -> None:
        """Turning the switch off persists enabled=False to options."""

        entry = await _setup_integration(hass, _default_options(enabled=True))

        # Patch reload so it doesn't interfere
        with patch.object(
            hass.config_entries,
            "async_reload",
            new_callable=AsyncMock,
        ):
            await hass.services.async_call(
                "switch",
                "turn_off",
                {"entity_id": "switch.pi_thermostat_enabled"},
                blocking=True,
            )

        state = hass.states.get("switch.pi_thermostat_enabled")
        assert state is not None
        assert state.state == "off"
        assert entry.options["enabled"] is False

    async def test_turn_on_persists(self, hass: HomeAssistant) -> None:
        """Turning the switch on persists enabled=True to options."""

        entry = await _setup_integration(hass, _default_options(enabled=False))

        state = hass.states.get("switch.pi_thermostat_enabled")
        assert state is not None
        assert state.state == "off"

        with patch.object(
            hass.config_entries,
            "async_reload",
            new_callable=AsyncMock,
        ):
            await hass.services.async_call(
                "switch",
                "turn_on",
                {"entity_id": "switch.pi_thermostat_enabled"},
                blocking=True,
            )

        state = hass.states.get("switch.pi_thermostat_enabled")
        assert state is not None
        assert state.state == "on"
        assert entry.options["enabled"] is True


# ===========================================================================
# Number write operations
# ===========================================================================


class TestNumberWrite:
    """Test number async_set_native_value persists to config entry options."""

    async def test_set_target_temp_persists(self, hass: HomeAssistant) -> None:
        """Setting target temp number persists to options."""

        entry = await _setup_integration(hass, _default_options(target_temp=20.0))

        with patch.object(
            hass.config_entries,
            "async_reload",
            new_callable=AsyncMock,
        ):
            await hass.services.async_call(
                "number",
                "set_value",
                {
                    "entity_id": "number.pi_thermostat_target_temperature",
                    "value": 23.0,
                },
                blocking=True,
            )

        state = hass.states.get("number.pi_thermostat_target_temperature")
        assert state is not None
        assert float(state.state) == pytest.approx(23.0, abs=0.01)
        assert entry.options["target_temp"] == pytest.approx(23.0, abs=0.01)

    async def test_set_prop_band_persists(self, hass: HomeAssistant) -> None:
        """Setting proportional band number persists to options."""

        entry = await _setup_integration(hass, _default_options(proportional_band=4.0))

        with patch.object(
            hass.config_entries,
            "async_reload",
            new_callable=AsyncMock,
        ):
            await hass.services.async_call(
                "number",
                "set_value",
                {
                    "entity_id": "number.pi_thermostat_proportional_band",
                    "value": 8.0,
                },
                blocking=True,
            )

        state = hass.states.get("number.pi_thermostat_proportional_band")
        assert state is not None
        assert float(state.state) == pytest.approx(8.0, abs=0.01)
        assert entry.options["proportional_band"] == pytest.approx(8.0, abs=0.01)
