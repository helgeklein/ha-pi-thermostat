"""Tests for ha_interface.py.

Tests cover:
- Exception classes: construction, attributes, messages.
- HomeAssistantInterface state reading:
  - _get_float_state: valid, unavailable, unknown, non-numeric.
  - _get_float_attribute: valid, unavailable, missing attr, non-numeric.
  - _get_str_attribute: valid, unavailable, missing attr, None attr.
- Public API temperature methods:
  - get_temperature, get_climate_current_temperature,
    get_target_temperature, get_climate_target_temperature.
- Public API climate attributes:
  - get_climate_hvac_action, get_climate_hvac_mode.
- Public API availability:
  - is_entity_available: available, unavailable, unknown, missing.
"""

from __future__ import annotations

from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant

from custom_components.pi_thermostat.ha_interface import (
    EntityUnavailableError,
    HomeAssistantInterface,
    InvalidSensorReadingError,
    PiThermostatHAError,
    ServiceCallError,
)
from custom_components.pi_thermostat.log import Log

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_interface(hass: HomeAssistant) -> HomeAssistantInterface:
    """Create a HomeAssistantInterface with a dummy logger."""

    logger = Log(entry_id="TEST01")
    return HomeAssistantInterface(hass, logger)


# ===========================================================================
# Exception classes
# ===========================================================================


class TestExceptions:
    """Test exception class construction and attributes."""

    def test_base_error(self) -> None:
        """PiThermostatHAError is an Exception."""

        err = PiThermostatHAError("test")
        assert isinstance(err, Exception)
        assert str(err) == "test"

    def test_entity_unavailable_error(self) -> None:
        """EntityUnavailableError stores entity_id."""

        err = EntityUnavailableError("sensor.temp")
        assert err.entity_id == "sensor.temp"
        assert "sensor.temp" in str(err)
        assert isinstance(err, PiThermostatHAError)

    def test_invalid_sensor_reading_error(self) -> None:
        """InvalidSensorReadingError stores entity_id and value."""

        err = InvalidSensorReadingError("sensor.temp", "NaN")
        assert err.entity_id == "sensor.temp"
        assert err.value == "NaN"
        assert "sensor.temp" in str(err)
        assert "NaN" in str(err)
        assert isinstance(err, PiThermostatHAError)

    def test_service_call_error(self) -> None:
        """ServiceCallError stores service, entity_id, error."""

        err = ServiceCallError("input_number.set_value", "input_number.out", "timeout")
        assert err.service == "input_number.set_value"
        assert err.entity_id == "input_number.out"
        assert err.error == "timeout"
        assert isinstance(err, PiThermostatHAError)


# ===========================================================================
# _get_float_state (tested via get_temperature)
# ===========================================================================


class TestGetFloatState:
    """Test float state reading via get_temperature."""

    async def test_valid_float(self, hass: HomeAssistant) -> None:
        """Returns float when state is a valid number."""

        hass.states.async_set("sensor.temp", "21.5")
        iface = _make_interface(hass)

        assert iface.get_temperature("sensor.temp") == 21.5

    async def test_integer_state(self, hass: HomeAssistant) -> None:
        """Returns float from integer state."""

        hass.states.async_set("sensor.temp", "20")
        iface = _make_interface(hass)

        assert iface.get_temperature("sensor.temp") == 20.0

    async def test_unavailable(self, hass: HomeAssistant) -> None:
        """Returns None when state is unavailable."""

        hass.states.async_set("sensor.temp", STATE_UNAVAILABLE)
        iface = _make_interface(hass)

        assert iface.get_temperature("sensor.temp") is None

    async def test_unknown(self, hass: HomeAssistant) -> None:
        """Returns None when state is unknown."""

        hass.states.async_set("sensor.temp", STATE_UNKNOWN)
        iface = _make_interface(hass)

        assert iface.get_temperature("sensor.temp") is None

    async def test_missing_entity(self, hass: HomeAssistant) -> None:
        """Returns None when entity does not exist."""

        iface = _make_interface(hass)

        assert iface.get_temperature("sensor.nonexistent") is None

    async def test_non_numeric(self, hass: HomeAssistant) -> None:
        """Returns None for non-numeric state value."""

        hass.states.async_set("sensor.temp", "not_a_number")
        iface = _make_interface(hass)

        assert iface.get_temperature("sensor.temp") is None

    async def test_empty_string(self, hass: HomeAssistant) -> None:
        """Returns None for empty string state."""

        hass.states.async_set("sensor.temp", "")
        iface = _make_interface(hass)

        assert iface.get_temperature("sensor.temp") is None


# ===========================================================================
# _get_float_attribute (tested via get_climate_current_temperature)
# ===========================================================================


class TestGetFloatAttribute:
    """Test float attribute reading via get_climate_current_temperature."""

    async def test_valid_attribute(self, hass: HomeAssistant) -> None:
        """Returns float when attribute is a valid number."""

        hass.states.async_set(
            "climate.room",
            "heat",
            {"current_temperature": 22.3},
        )
        iface = _make_interface(hass)

        assert iface.get_climate_current_temperature("climate.room") == 22.3

    async def test_integer_attribute(self, hass: HomeAssistant) -> None:
        """Returns float from integer attribute."""

        hass.states.async_set(
            "climate.room",
            "heat",
            {"current_temperature": 20},
        )
        iface = _make_interface(hass)

        assert iface.get_climate_current_temperature("climate.room") == 20.0

    async def test_unavailable_entity(self, hass: HomeAssistant) -> None:
        """Returns None when entity is unavailable."""

        hass.states.async_set(
            "climate.room",
            STATE_UNAVAILABLE,
            {"current_temperature": 22.0},
        )
        iface = _make_interface(hass)

        assert iface.get_climate_current_temperature("climate.room") is None

    async def test_missing_attribute(self, hass: HomeAssistant) -> None:
        """Returns None when attribute does not exist."""

        hass.states.async_set("climate.room", "heat", {})
        iface = _make_interface(hass)

        assert iface.get_climate_current_temperature("climate.room") is None

    async def test_none_attribute(self, hass: HomeAssistant) -> None:
        """Returns None when attribute value is None."""

        hass.states.async_set(
            "climate.room",
            "heat",
            {"current_temperature": None},
        )
        iface = _make_interface(hass)

        assert iface.get_climate_current_temperature("climate.room") is None

    async def test_non_numeric_attribute(self, hass: HomeAssistant) -> None:
        """Returns None for non-numeric attribute value."""

        hass.states.async_set(
            "climate.room",
            "heat",
            {"current_temperature": "error"},
        )
        iface = _make_interface(hass)

        assert iface.get_climate_current_temperature("climate.room") is None

    async def test_missing_entity(self, hass: HomeAssistant) -> None:
        """Returns None when entity does not exist."""

        iface = _make_interface(hass)

        assert iface.get_climate_current_temperature("climate.nonexistent") is None


# ===========================================================================
# _get_str_attribute (tested via get_climate_hvac_action)
# ===========================================================================


class TestGetStrAttribute:
    """Test string attribute reading via get_climate_hvac_action."""

    async def test_valid_attribute(self, hass: HomeAssistant) -> None:
        """Returns string when attribute exists."""

        hass.states.async_set(
            "climate.room",
            "heat",
            {"hvac_action": "heating"},
        )
        iface = _make_interface(hass)

        assert iface.get_climate_hvac_action("climate.room") == "heating"

    async def test_unavailable_entity(self, hass: HomeAssistant) -> None:
        """Returns None when entity is unavailable."""

        hass.states.async_set(
            "climate.room",
            STATE_UNAVAILABLE,
            {"hvac_action": "heating"},
        )
        iface = _make_interface(hass)

        assert iface.get_climate_hvac_action("climate.room") is None

    async def test_missing_attribute(self, hass: HomeAssistant) -> None:
        """Returns None when attribute does not exist."""

        hass.states.async_set("climate.room", "heat", {})
        iface = _make_interface(hass)

        assert iface.get_climate_hvac_action("climate.room") is None

    async def test_missing_entity(self, hass: HomeAssistant) -> None:
        """Returns None when entity does not exist."""

        iface = _make_interface(hass)

        assert iface.get_climate_hvac_action("climate.nonexistent") is None


# ===========================================================================
# Public API — additional temperature methods
# ===========================================================================


class TestTargetTemperature:
    """Test get_target_temperature (delegates to _get_float_state)."""

    async def test_valid(self, hass: HomeAssistant) -> None:
        """Returns float for valid number state."""

        hass.states.async_set("input_number.setpoint", "23.0")
        iface = _make_interface(hass)

        assert iface.get_target_temperature("input_number.setpoint") == 23.0

    async def test_unavailable(self, hass: HomeAssistant) -> None:
        """Returns None for unavailable entity."""

        hass.states.async_set("input_number.setpoint", STATE_UNAVAILABLE)
        iface = _make_interface(hass)

        assert iface.get_target_temperature("input_number.setpoint") is None


class TestClimateTargetTemperature:
    """Test get_climate_target_temperature (reads 'temperature' attribute)."""

    async def test_valid(self, hass: HomeAssistant) -> None:
        """Returns float when temperature attribute exists."""

        hass.states.async_set(
            "climate.room",
            "heat",
            {"temperature": 24.0},
        )
        iface = _make_interface(hass)

        assert iface.get_climate_target_temperature("climate.room") == 24.0

    async def test_missing(self, hass: HomeAssistant) -> None:
        """Returns None when temperature attribute is missing."""

        hass.states.async_set("climate.room", "heat", {})
        iface = _make_interface(hass)

        assert iface.get_climate_target_temperature("climate.room") is None


# ===========================================================================
# Public API — climate HVAC mode
# ===========================================================================


class TestGetClimateHvacMode:
    """Test get_climate_hvac_mode (reads main state)."""

    async def test_returns_state(self, hass: HomeAssistant) -> None:
        """Returns the main state as a string."""

        hass.states.async_set("climate.room", "heat")
        iface = _make_interface(hass)

        assert iface.get_climate_hvac_mode("climate.room") == "heat"

    async def test_off_state(self, hass: HomeAssistant) -> None:
        """Returns 'off' when climate is off."""

        hass.states.async_set("climate.room", "off")
        iface = _make_interface(hass)

        assert iface.get_climate_hvac_mode("climate.room") == "off"

    async def test_unavailable(self, hass: HomeAssistant) -> None:
        """Returns None when climate entity is unavailable."""

        hass.states.async_set("climate.room", STATE_UNAVAILABLE)
        iface = _make_interface(hass)

        assert iface.get_climate_hvac_mode("climate.room") is None

    async def test_missing_entity(self, hass: HomeAssistant) -> None:
        """Returns None when entity does not exist."""

        iface = _make_interface(hass)

        assert iface.get_climate_hvac_mode("climate.nonexistent") is None


# ===========================================================================
# Public API — is_entity_available
# ===========================================================================


class TestIsEntityAvailable:
    """Test is_entity_available."""

    async def test_available(self, hass: HomeAssistant) -> None:
        """Returns True for available entity."""

        hass.states.async_set("sensor.temp", "21.0")
        iface = _make_interface(hass)

        assert iface.is_entity_available("sensor.temp") is True

    async def test_unavailable(self, hass: HomeAssistant) -> None:
        """Returns False for unavailable entity."""

        hass.states.async_set("sensor.temp", STATE_UNAVAILABLE)
        iface = _make_interface(hass)

        assert iface.is_entity_available("sensor.temp") is False

    async def test_unknown(self, hass: HomeAssistant) -> None:
        """Returns False for unknown entity state."""

        hass.states.async_set("sensor.temp", STATE_UNKNOWN)
        iface = _make_interface(hass)

        assert iface.is_entity_available("sensor.temp") is False

    async def test_missing(self, hass: HomeAssistant) -> None:
        """Returns False for non-existent entity."""

        iface = _make_interface(hass)

        assert iface.is_entity_available("sensor.nonexistent") is False
