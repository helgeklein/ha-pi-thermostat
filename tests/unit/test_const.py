"""Unit tests for const.py.

Tests that constants are defined correctly, enums have expected members, and
string values match expectations for serialization/translation lookups.
"""

from __future__ import annotations

from custom_components.pi_thermostat.const import (
    DEFAULT_INT_TIME,
    DEFAULT_ITERM_STARTUP_VALUE,
    DEFAULT_OUTPUT_MAX,
    DEFAULT_OUTPUT_MIN,
    DEFAULT_PROP_BAND,
    DOMAIN,
    ERROR_CLIMATE_TARGET_REQUIRES_CLIMATE,
    ERROR_HEAT_COOL_REQUIRES_CLIMATE,
    ERROR_NO_TEMP_SOURCE,
    INTEGRATION_NAME,
    NUMBER_KEY_INT_TIME,
    NUMBER_KEY_OUTPUT_MAX,
    NUMBER_KEY_OUTPUT_MIN,
    NUMBER_KEY_PROP_BAND,
    NUMBER_KEY_TARGET_TEMP,
    NUMBER_KEY_UPDATE_INTERVAL,
    SENSOR_FAULT_GRACE_PERIOD_SECONDS,
    SENSOR_KEY_CURRENT_TEMP,
    SENSOR_KEY_DEVIATION,
    SENSOR_KEY_I_TERM,
    SENSOR_KEY_OUTPUT,
    SENSOR_KEY_P_TERM,
    SENSOR_KEY_TARGET_TEMP,
    SWITCH_KEY_ENABLED,
    UPDATE_INTERVAL_DEFAULT_SECONDS,
    ITermStartupMode,
    OperatingMode,
    SensorFaultMode,
)

# ---------------------------------------------------------------------------
# Domain identity
# ---------------------------------------------------------------------------


class TestDomainIdentity:
    """Test domain and integration name constants."""

    def test_domain(self) -> None:
        """Domain string matches expected value."""

        assert DOMAIN == "pi_thermostat"

    def test_integration_name(self) -> None:
        """Integration display name."""

        assert INTEGRATION_NAME == "PI Thermostat"


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------


class TestDefaults:
    """Test default values are sensible."""

    def test_update_interval(self) -> None:
        """Default update interval is 60 seconds."""

        assert UPDATE_INTERVAL_DEFAULT_SECONDS == 60

    def test_prop_band(self) -> None:
        """Default proportional band is 4 K."""

        assert DEFAULT_PROP_BAND == 4.0

    def test_int_time(self) -> None:
        """Default integral time is 120 minutes."""

        assert DEFAULT_INT_TIME == 120.0

    def test_output_min(self) -> None:
        """Default output minimum is 0%."""

        assert DEFAULT_OUTPUT_MIN == 0.0

    def test_output_max(self) -> None:
        """Default output maximum is 100%."""

        assert DEFAULT_OUTPUT_MAX == 100.0

    def test_grace_period(self) -> None:
        """Sensor fault grace period is 300 seconds (5 min)."""

        assert SENSOR_FAULT_GRACE_PERIOD_SECONDS == 300

    def test_iterm_startup_value(self) -> None:
        """Default I-term startup value is 0%."""

        assert DEFAULT_ITERM_STARTUP_VALUE == 0.0


# ---------------------------------------------------------------------------
# Entity keys
# ---------------------------------------------------------------------------


class TestEntityKeys:
    """Test entity key constants are unique non-empty strings."""

    def test_sensor_keys_unique(self) -> None:
        """Sensor keys are unique."""

        keys = [
            SENSOR_KEY_OUTPUT,
            SENSOR_KEY_DEVIATION,
            SENSOR_KEY_CURRENT_TEMP,
            SENSOR_KEY_TARGET_TEMP,
            SENSOR_KEY_P_TERM,
            SENSOR_KEY_I_TERM,
        ]
        assert len(keys) == len(set(keys))

    def test_number_keys_unique(self) -> None:
        """Number keys are unique."""

        keys = [
            NUMBER_KEY_PROP_BAND,
            NUMBER_KEY_INT_TIME,
            NUMBER_KEY_TARGET_TEMP,
            NUMBER_KEY_OUTPUT_MIN,
            NUMBER_KEY_OUTPUT_MAX,
            NUMBER_KEY_UPDATE_INTERVAL,
        ]
        assert len(keys) == len(set(keys))

    def test_switch_key(self) -> None:
        """Switch key matches expected value."""

        assert SWITCH_KEY_ENABLED == "enabled"


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class TestOperatingMode:
    """Test OperatingMode enum."""

    def test_members(self) -> None:
        """Has exactly 3 members."""

        assert len(OperatingMode) == 3

    def test_heat_cool(self) -> None:
        """heat_cool value corresponds to HVACMode.HEAT_COOL."""

        assert OperatingMode.HEAT_COOL == "heat_cool"

    def test_heat(self) -> None:
        """heat value."""

        assert OperatingMode.HEAT == "heat"

    def test_cool(self) -> None:
        """cool value."""

        assert OperatingMode.COOL == "cool"

    def test_is_str(self) -> None:
        """OperatingMode values are strings (StrEnum)."""

        for mode in OperatingMode:
            assert isinstance(mode, str)


class TestSensorFaultMode:
    """Test SensorFaultMode enum."""

    def test_members(self) -> None:
        """Has exactly 2 members."""

        assert len(SensorFaultMode) == 2

    def test_shutdown(self) -> None:
        """Shutdown value."""

        assert SensorFaultMode.SHUTDOWN == "shutdown"

    def test_hold(self) -> None:
        """Hold value."""

        assert SensorFaultMode.HOLD == "hold"


class TestITermStartupMode:
    """Test ITermStartupMode enum."""

    def test_members(self) -> None:
        """Has exactly 3 members."""

        assert len(ITermStartupMode) == 3

    def test_last(self) -> None:
        """Last value."""

        assert ITermStartupMode.LAST == "last"

    def test_fixed(self) -> None:
        """Fixed value."""

        assert ITermStartupMode.FIXED == "fixed"

    def test_zero(self) -> None:
        """Zero value."""

        assert ITermStartupMode.ZERO == "zero"

    def test_is_str(self) -> None:
        """ITermStartupMode values are strings (StrEnum)."""

        for mode in ITermStartupMode:
            assert isinstance(mode, str)


# ---------------------------------------------------------------------------
# Error constants
# ---------------------------------------------------------------------------


class TestErrorConstants:
    """Test error translation keys."""

    def test_no_temp_source(self) -> None:
        """Error key for missing temp source."""

        assert ERROR_NO_TEMP_SOURCE == "no_temp_source"

    def test_heat_cool_requires_climate(self) -> None:
        """Error key for heat_cool without climate entity."""

        assert ERROR_HEAT_COOL_REQUIRES_CLIMATE == "heat_cool_requires_climate"

    def test_climate_target_requires_climate(self) -> None:
        """Error key for climate target without climate entity."""

        assert ERROR_CLIMATE_TARGET_REQUIRES_CLIMATE == "climate_target_requires_climate"
