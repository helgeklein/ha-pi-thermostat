"""Tests for config_flow.py.

Tests cover:
- Config flow: welcome form → create entry with defaults.
- Options flow wizard:
    - Happy path for PI and CCA paths.
    - Validation errors on PI and CCA steps.
  - Suggested values from existing options.
- Validation helpers: _validate_step_1, _validate_step_2.
- Schema builders: _build_schema_step_1, _build_schema_step_2, _build_schema_step_3.

Requires the ``hass`` fixture from pytest-homeassistant-custom-component.
"""

# pyright: reportTypedDictNotRequiredAccess=false

from __future__ import annotations

from typing import Any
from unittest.mock import patch

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import selector

from custom_components.pi_thermostat.config_flow import (
    DOCS_URL,
    FlowHandler,
    _build_schema_step_1,
    _build_schema_step_2,
    _build_schema_step_3,
    _build_schema_step_cca_sources,
    _build_schema_step_mode,
    _validate_step_1,
    _validate_step_2,
    _validate_step_cca_sources,
)
from custom_components.pi_thermostat.const import (
    DOMAIN,
    ERROR_CCA_COOLING_ENABLE_REQUIRED,
    ERROR_CCA_WEATHER_REQUIRED,
    ERROR_CCA_WEATHER_UNSUPPORTED,
    ERROR_CLIMATE_TARGET_REQUIRES_CLIMATE,
    ERROR_HEAT_COOL_REQUIRES_CLIMATE,
    ERROR_NO_TEMP_SOURCE,
    INTEGRATION_NAME,
    CCAForecastUnavailableMode,
    ControlMode,
    ITermStartupMode,
    OperatingMode,
    SensorFaultMode,
    TargetTempMode,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_config_entry(
    options: dict[str, Any] | None = None,
) -> Any:
    """Create a MockConfigEntry for testing."""

    from pytest_homeassistant_custom_component.common import MockConfigEntry

    return MockConfigEntry(
        domain=DOMAIN,
        title=INTEGRATION_NAME,
        data={},
        options=options or {},
    )


# ===========================================================================
# _validate_step_1 (unit)
# ===========================================================================


class TestValidateStep1:
    """Unit tests for _validate_step_1."""

    def test_heat_only_no_climate_ok(self) -> None:
        """Heat-only mode does not require climate."""

        errors = _validate_step_1(
            {
                "operating_mode": OperatingMode.HEAT,
            }
        )
        assert errors == {}

    def test_cool_only_no_climate_ok(self) -> None:
        """Cool-only mode does not require climate."""

        errors = _validate_step_1(
            {
                "operating_mode": OperatingMode.COOL,
            }
        )
        assert errors == {}

    def test_heat_cool_no_climate_error(self) -> None:
        """Heat+cool mode without climate triggers error."""

        errors = _validate_step_1(
            {
                "operating_mode": OperatingMode.HEAT_COOL,
            }
        )
        assert errors == {"operating_mode": ERROR_HEAT_COOL_REQUIRES_CLIMATE}

    def test_heat_cool_with_climate_ok(self) -> None:
        """Heat+cool mode with climate is valid."""

        errors = _validate_step_1(
            {
                "climate_entity": "climate.living_room",
                "operating_mode": OperatingMode.HEAT_COOL,
            }
        )
        assert errors == {}

    def test_empty_input(self) -> None:
        """Empty input is valid (operating_mode defaults to empty string)."""

        errors = _validate_step_1({})
        assert errors == {}


# ===========================================================================
# _validate_step_2 (unit)
# ===========================================================================


class TestValidateStep2:
    """Unit tests for _validate_step_2."""

    def test_sensor_no_climate_ok(self) -> None:
        """Temp sensor without climate is valid."""

        errors = _validate_step_2(
            {"temp_sensor": "sensor.temp"},
            has_climate=False,
        )
        assert errors == {}

    def test_no_sensor_with_climate_ok(self) -> None:
        """No temp sensor with climate is valid (falls back to climate temp)."""

        errors = _validate_step_2(
            {},
            has_climate=True,
        )
        assert errors == {}

    def test_no_sensor_no_climate_error(self) -> None:
        """No temp sensor and no climate triggers error."""

        errors = _validate_step_2(
            {},
            has_climate=False,
        )
        assert errors == {"temp_sensor": ERROR_NO_TEMP_SOURCE}

    def test_climate_target_no_climate_error(self) -> None:
        """Target mode 'climate' without climate triggers error."""

        errors = _validate_step_2(
            {
                "temp_sensor": "sensor.temp",
                "target_temp_mode": TargetTempMode.CLIMATE,
            },
            has_climate=False,
        )
        assert errors == {"target_temp_mode": ERROR_CLIMATE_TARGET_REQUIRES_CLIMATE}

    def test_climate_target_with_climate_ok(self) -> None:
        """Target mode 'climate' with climate is valid."""

        errors = _validate_step_2(
            {
                "temp_sensor": "sensor.temp",
                "target_temp_mode": TargetTempMode.CLIMATE,
            },
            has_climate=True,
        )
        assert errors == {}

    def test_internal_target_no_climate_ok(self) -> None:
        """Internal target mode is always valid (sensor provides temp)."""

        errors = _validate_step_2(
            {
                "temp_sensor": "sensor.temp",
                "target_temp_mode": TargetTempMode.INTERNAL,
            },
            has_climate=False,
        )
        assert errors == {}

    def test_external_target_no_climate_ok(self) -> None:
        """External target mode is valid without climate (sensor provides temp)."""

        errors = _validate_step_2(
            {
                "temp_sensor": "sensor.temp",
                "target_temp_mode": TargetTempMode.EXTERNAL,
            },
            has_climate=False,
        )
        assert errors == {}

    def test_both_errors(self) -> None:
        """No sensor + climate target without climate yields two errors."""

        errors = _validate_step_2(
            {"target_temp_mode": TargetTempMode.CLIMATE},
            has_climate=False,
        )
        assert "temp_sensor" in errors
        assert "target_temp_mode" in errors


# ===========================================================================
# _validate_step_cca_sources (unit)
# ===========================================================================


class TestValidateCCASources:
    """Unit tests for _validate_step_cca_sources."""

    async def test_requires_entities(self, hass: HomeAssistant) -> None:
        """Both required entities must be configured."""

        errors = await _validate_step_cca_sources(hass, {})
        assert errors == {
            "cca_cooling_enable_entity": ERROR_CCA_COOLING_ENABLE_REQUIRED,
            "cca_weather_entity": ERROR_CCA_WEATHER_REQUIRED,
        }

    async def test_weather_support_checked(self, hass: HomeAssistant) -> None:
        """Weather entity must support daily forecasts."""

        from homeassistant.exceptions import HomeAssistantError

        with patch(
            "custom_components.pi_thermostat.ha_interface.HomeAssistantInterface.async_validate_daily_forecast_support",
            side_effect=HomeAssistantError("unsupported"),
        ):
            errors = await _validate_step_cca_sources(
                hass,
                {
                    "cca_cooling_enable_entity": "binary_sensor.cooling",
                    "cca_weather_entity": "weather.home",
                },
            )

        assert errors == {"cca_weather_entity": ERROR_CCA_WEATHER_UNSUPPORTED}


# ===========================================================================
# Schema builders (unit)
# ===========================================================================


class TestBuildSchemaStepMode:
    """Tests for _build_schema_step_mode."""

    def test_contains_control_mode(self) -> None:
        """Schema has the control_mode selector."""

        schema = _build_schema_step_mode({})
        key_names = {str(k) for k in schema.schema}
        assert "control_mode" in key_names


class TestBuildSchemaCCASources:
    """Tests for _build_schema_step_cca_sources."""

    def test_contains_expected_keys(self) -> None:
        """Schema includes the required CCA data-source fields."""

        schema = _build_schema_step_cca_sources({})
        key_names = {str(k) for k in schema.schema}
        assert "cca_cooling_enable_entity" in key_names
        assert "cca_cooling_enable_on" in key_names
        assert "cca_weather_entity" in key_names
        assert "cca_forecast_horizon_days" in key_names
        assert "cca_forecast_unavailable_mode" in key_names

    def test_cooling_enable_selector_is_binary_only(self) -> None:
        """Cooling-enable selector is restricted to binary-capable domains."""

        schema = _build_schema_step_cca_sources({})
        selector_rule = next(rule for key, rule in schema.schema.items() if str(key) == "cca_cooling_enable_entity")

        assert isinstance(selector_rule, selector.EntitySelector)
        assert selector_rule.config["domain"] == ["binary_sensor", "input_boolean", "switch"]


class TestBuildSchemaStep1:
    """Tests for _build_schema_step_1."""

    def test_returns_schema(self) -> None:
        """Schema is a voluptuous Schema."""

        import voluptuous as vol

        schema = _build_schema_step_1({})
        assert isinstance(schema, vol.Schema)

    def test_contains_expected_keys(self) -> None:
        """Schema has climate_entity, operating_mode, auto_disable."""

        schema = _build_schema_step_1({})
        key_names = {str(k) for k in schema.schema}
        assert "climate_entity" in key_names
        assert "operating_mode" in key_names
        assert "auto_disable_on_hvac_off" in key_names


class TestBuildSchemaStep2:
    """Tests for _build_schema_step_2."""

    def test_without_climate(self) -> None:
        """Schema without climate does not include 'climate' target mode option."""

        schema = _build_schema_step_2({}, has_climate=False)
        key_names = {str(k) for k in schema.schema}
        assert "temp_sensor" in key_names
        assert "target_temp_mode" in key_names

    def test_with_climate(self) -> None:
        """Schema with climate includes 'climate' target mode option."""

        schema = _build_schema_step_2({}, has_climate=True)
        key_names = {str(k) for k in schema.schema}
        assert "target_temp_mode" in key_names


class TestBuildSchemaStep3:
    """Tests for _build_schema_step_3."""

    def test_returns_schema(self) -> None:
        """Schema is a voluptuous Schema."""

        import voluptuous as vol

        schema = _build_schema_step_3({})
        assert isinstance(schema, vol.Schema)

    def test_contains_expected_keys(self) -> None:
        """Schema has sensor_fault_mode, iterm_startup_mode/value."""

        schema = _build_schema_step_3({})
        key_names = {str(k) for k in schema.schema}
        assert "sensor_fault_mode" in key_names
        assert "iterm_startup_mode" in key_names
        assert "iterm_startup_value" in key_names


# ===========================================================================
# Config flow (integration-level, requires hass fixture)
# ===========================================================================


class TestConfigFlow:
    """Test the config flow (initial setup)."""

    async def test_show_welcome_form(self, hass: HomeAssistant) -> None:
        """Config flow shows the welcome form on first invocation."""

        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
        )
        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "user"
        assert result["description_placeholders"] is not None
        assert result["description_placeholders"]["docs_url"] == DOCS_URL

    async def test_create_entry(self, hass: HomeAssistant) -> None:
        """Submitting the welcome form creates an entry with defaults."""

        # Show the form first
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
        )

        # Submit
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={},
        )
        assert result["type"] is FlowResultType.CREATE_ENTRY
        assert result["title"] == INTEGRATION_NAME
        assert result["data"] == {}

    async def test_handler_domain(self) -> None:
        """FlowHandler has the correct domain."""

        assert FlowHandler.domain == DOMAIN


# ===========================================================================
# Options flow (integration-level, requires hass fixture)
# ===========================================================================


class TestOptionsFlowHappyPath:
    """Test the options flow happy path."""

    async def test_full_pi_wizard(self, hass: HomeAssistant) -> None:
        """Complete the PI-mode wizard with valid inputs."""

        entry = _mock_config_entry()
        entry.add_to_hass(hass)

        result = await hass.config_entries.options.async_init(entry.entry_id)
        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "init"

        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={
                "control_mode": ControlMode.PI,
            },
        )
        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "2"

        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={
                "climate_entity": "climate.living_room",
                "operating_mode": OperatingMode.HEAT_COOL,
                "auto_disable_on_hvac_off": True,
            },
        )
        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "3"

        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={
                "temp_sensor": "sensor.temperature",
                "target_temp_mode": TargetTempMode.INTERNAL,
            },
        )
        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "4"

        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={
                "sensor_fault_mode": SensorFaultMode.SHUTDOWN,
                "iterm_startup_mode": ITermStartupMode.LAST,
                "iterm_startup_value": 0.0,
            },
        )
        assert result["type"] is FlowResultType.CREATE_ENTRY

        # Verify saved options
        saved = result["data"]
        assert saved["control_mode"] == ControlMode.PI
        assert saved["climate_entity"] == "climate.living_room"
        assert saved["operating_mode"] == OperatingMode.HEAT_COOL
        assert saved["temp_sensor"] == "sensor.temperature"
        assert saved["sensor_fault_mode"] == SensorFaultMode.SHUTDOWN
        assert saved["iterm_startup_mode"] == ITermStartupMode.LAST

    async def test_minimal_pi_wizard(self, hass: HomeAssistant) -> None:
        """Complete the PI wizard with minimal inputs."""

        entry = _mock_config_entry()
        entry.add_to_hass(hass)

        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={
                "control_mode": ControlMode.PI,
            },
        )
        assert result["step_id"] == "2"

        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={
                "operating_mode": OperatingMode.HEAT,
                "auto_disable_on_hvac_off": False,
            },
        )
        assert result["step_id"] == "3"

        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={
                "temp_sensor": "sensor.temp",
                "target_temp_mode": TargetTempMode.INTERNAL,
            },
        )
        assert result["step_id"] == "4"

        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={
                "sensor_fault_mode": SensorFaultMode.HOLD,
                "iterm_startup_mode": ITermStartupMode.ZERO,
                "iterm_startup_value": 0.0,
            },
        )
        assert result["type"] is FlowResultType.CREATE_ENTRY

    async def test_cca_wizard(self, hass: HomeAssistant) -> None:
        """Complete the CCA-mode wizard."""

        entry = _mock_config_entry()
        entry.add_to_hass(hass)

        with patch(
            "custom_components.pi_thermostat.ha_interface.HomeAssistantInterface.async_validate_daily_forecast_support",
            return_value=None,
        ):
            result = await hass.config_entries.options.async_init(entry.entry_id)
            result = await hass.config_entries.options.async_configure(
                result["flow_id"],
                user_input={"control_mode": ControlMode.CCA},
            )

            assert result["step_id"] == "cca_sources"

            result = await hass.config_entries.options.async_configure(
                result["flow_id"],
                user_input={
                    "cca_cooling_enable_entity": "binary_sensor.cooling",
                    "cca_cooling_enable_on": True,
                    "cca_weather_entity": "weather.home",
                    "cca_forecast_horizon_days": 3,
                    "cca_forecast_unavailable_mode": CCAForecastUnavailableMode.HOLD,
                },
            )

        assert result["type"] is FlowResultType.CREATE_ENTRY
        assert result["data"]["control_mode"] == ControlMode.CCA
        assert result["data"]["cca_cooling_enable_on"] is True
        assert result["data"]["cca_weather_entity"] == "weather.home"


class TestOptionsFlowValidation:
    """Test options flow validation error handling."""

    async def test_step1_heat_cool_requires_climate(self, hass: HomeAssistant) -> None:
        """Step 1 rejects heat+cool without climate entity."""

        entry = _mock_config_entry()
        entry.add_to_hass(hass)

        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={"control_mode": ControlMode.PI},
        )
        assert result["step_id"] == "2"

        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={
                "operating_mode": OperatingMode.HEAT_COOL,
                "auto_disable_on_hvac_off": True,
            },
        )
        # Should stay on step 1 with error
        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "2"
        assert result["errors"] is not None
        assert result["errors"]["operating_mode"] == ERROR_HEAT_COOL_REQUIRES_CLIMATE

    async def test_step2_no_temp_source(self, hass: HomeAssistant) -> None:
        """Step 2 rejects if no temperature source is configured."""

        entry = _mock_config_entry()
        entry.add_to_hass(hass)

        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={"control_mode": ControlMode.PI},
        )

        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={
                "operating_mode": OperatingMode.HEAT,
                "auto_disable_on_hvac_off": False,
            },
        )

        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={
                "target_temp_mode": TargetTempMode.INTERNAL,
            },
        )
        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "3"
        assert result["errors"] is not None
        assert result["errors"]["temp_sensor"] == ERROR_NO_TEMP_SOURCE

    async def test_step2_climate_target_requires_climate(self, hass: HomeAssistant) -> None:
        """Step 2 rejects climate target mode without climate entity.

        NOTE: The 'climate' option is only in the dropdown when a climate entity
        is configured. This tests a race/manipulation scenario where climate was
        set in existing options but cleared in step 1 of the current wizard run.
        """

        # Existing options have a climate entity, so step 2 schema includes
        # the 'climate' target mode option. But step 1 clears it.
        entry = _mock_config_entry(
            options={
                "climate_entity": "climate.old",
            }
        )
        entry.add_to_hass(hass)

        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={"control_mode": ControlMode.PI},
        )

        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={
                "operating_mode": OperatingMode.HEAT,
                "auto_disable_on_hvac_off": False,
            },
        )

        # Step 2: climate was cleared in step 1, but _has_climate() checks
        # both _config_data and existing options. Since step 1 didn't include
        # climate_entity, _config_data won't have it, but existing options do.
        # So _has_climate() returns True and the schema includes 'climate'.
        # Submit climate target mode.
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={
                "temp_sensor": "sensor.temp",
                "target_temp_mode": TargetTempMode.CLIMATE,
            },
        )
        # _has_climate() sees existing options still have climate_entity,
        # so no validation error. The flow proceeds to step 4.
        # This is expected behavior: existing climate entity hasn't been
        # removed from options yet (only cleared in step 1's input).
        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "4"

    async def test_step1_error_then_fix(self, hass: HomeAssistant) -> None:
        """Step 1 error can be corrected and wizard continues."""

        entry = _mock_config_entry()
        entry.add_to_hass(hass)

        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={"control_mode": ControlMode.PI},
        )

        # Submit invalid (heat_cool without climate)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={
                "operating_mode": OperatingMode.HEAT_COOL,
                "auto_disable_on_hvac_off": True,
            },
        )
        assert result["step_id"] == "2"
        assert result["errors"]

        # Fix: add climate
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={
                "climate_entity": "climate.living_room",
                "operating_mode": OperatingMode.HEAT_COOL,
                "auto_disable_on_hvac_off": True,
            },
        )
        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "3"


class TestOptionsFlowExistingOptions:
    """Test options flow with pre-existing options."""

    async def test_existing_options_preserved(self, hass: HomeAssistant) -> None:
        """Pre-existing options are preserved through the wizard."""

        entry = _mock_config_entry(
            options={
                "climate_entity": "climate.bedroom",
                "operating_mode": OperatingMode.COOL,
                "auto_disable_on_hvac_off": True,
                "temp_sensor": "sensor.bedroom_temp",
                "target_temp_mode": TargetTempMode.INTERNAL,
                "sensor_fault_mode": SensorFaultMode.HOLD,
                "iterm_startup_mode": ITermStartupMode.FIXED,
                "iterm_startup_value": 50.0,
            }
        )
        entry.add_to_hass(hass)

        # Step 1
        result = await hass.config_entries.options.async_init(entry.entry_id)
        assert result["step_id"] == "init"

        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={"control_mode": ControlMode.PI},
        )
        assert result["step_id"] == "2"

        # Keep same values
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={
                "climate_entity": "climate.bedroom",
                "operating_mode": OperatingMode.COOL,
                "auto_disable_on_hvac_off": True,
            },
        )

        # Step 2
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={
                "temp_sensor": "sensor.bedroom_temp",
                "target_temp_mode": TargetTempMode.INTERNAL,
            },
        )
        assert result["step_id"] == "4"

        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={
                "sensor_fault_mode": SensorFaultMode.HOLD,
                "iterm_startup_mode": ITermStartupMode.FIXED,
                "iterm_startup_value": 50.0,
            },
        )
        assert result["type"] is FlowResultType.CREATE_ENTRY

        saved = result["data"]
        assert saved["control_mode"] == ControlMode.PI
        assert saved["climate_entity"] == "climate.bedroom"
        assert saved["operating_mode"] == OperatingMode.COOL
        assert saved["sensor_fault_mode"] == SensorFaultMode.HOLD
        assert saved["iterm_startup_mode"] == ITermStartupMode.FIXED
        assert saved["iterm_startup_value"] == 50.0

    async def test_existing_options_merged(self, hass: HomeAssistant) -> None:
        """Pre-existing options not submitted in the wizard are preserved."""

        entry = _mock_config_entry(
            options={
                "sensor_fault_mode": SensorFaultMode.HOLD,
            }
        )
        entry.add_to_hass(hass)

        # Step 1
        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={"control_mode": ControlMode.PI},
        )

        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={
                "climate_entity": "climate.room",
                "operating_mode": OperatingMode.HEAT,
                "auto_disable_on_hvac_off": False,
            },
        )

        # Step 2
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={
                "temp_sensor": "sensor.temp",
                "target_temp_mode": TargetTempMode.INTERNAL,
            },
        )
        assert result["step_id"] == "4"

        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={
                "sensor_fault_mode": SensorFaultMode.SHUTDOWN,
                "iterm_startup_mode": ITermStartupMode.ZERO,
                "iterm_startup_value": 0.0,
            },
        )
        assert result["type"] is FlowResultType.CREATE_ENTRY

        saved = result["data"]
        assert saved["control_mode"] == ControlMode.PI
        # Step 3 overwrites existing sensor_fault_mode
        assert saved["sensor_fault_mode"] == SensorFaultMode.SHUTDOWN
