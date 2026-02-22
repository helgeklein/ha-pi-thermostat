"""Config flow and options flow for PI Thermostat integration.

The config flow is minimal: it creates an entry with default settings and no
user-configurable fields. All real configuration happens in the options flow.

The options flow has three steps:
  1. Climate Entity & Operating Mode
  2. Temperature Sensors & Target
  3. Output & Sensor Fault Mode

PI tuning parameters and update interval are adjusted at runtime via number
entities, not the options flow.
"""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.const import Platform
from homeassistant.helpers import selector

from .config import ConfKeys, resolve
from .const import (
    DOMAIN,
    ERROR_CLIMATE_TARGET_REQUIRES_CLIMATE,
    ERROR_HEAT_COOL_REQUIRES_CLIMATE,
    ERROR_NO_TEMP_SOURCE,
    INTEGRATION_NAME,
    TARGET_TEMP_MODE_CLIMATE,
    TARGET_TEMP_MODE_EXTERNAL,
    TARGET_TEMP_MODE_INTERNAL,
    ITermStartupMode,
    OperatingMode,
    SensorFaultMode,
)
from .log import Log

# ---------------------------------------------------------------------------
# Selector translation keys (used by SelectSelector to look up labels)
# ---------------------------------------------------------------------------

SELECTOR_KEY_OPERATING_MODE: str = "operating_mode"
SELECTOR_KEY_TARGET_TEMP_MODE: str = "target_temp_mode"
SELECTOR_KEY_SENSOR_FAULT_MODE: str = "sensor_fault_mode"
SELECTOR_KEY_ITERM_STARTUP_MODE: str = "iterm_startup_mode"

# ---------------------------------------------------------------------------
# Documentation URL shown in the config flow welcome page
# ---------------------------------------------------------------------------

DOCS_URL: str = "https://ha-pi-thermostat.helgeklein.com/"

# ---------------------------------------------------------------------------
# Entity selector domains
# ---------------------------------------------------------------------------

DOMAINS_OUTPUT_ENTITY: list[str] = ["input_number", Platform.NUMBER]


# ===========================================================================
# Schema builders
# ===========================================================================


#
# _build_schema_step_1
#
def _build_schema_step_1(defaults: dict[str, Any]) -> vol.Schema:
    """Build the voluptuous schema for step 1: Climate Entity & Operating Mode.

    Args:
        defaults: Current/default values keyed by ConfKeys string values.

    Returns:
        Schema for the step 1 form.
    """

    resolved = resolve(defaults)
    schema: dict[vol.Marker, Any] = {}

    # Climate entity (optional)
    schema[vol.Optional(ConfKeys.CLIMATE_ENTITY.value)] = selector.EntitySelector(selector.EntitySelectorConfig(domain=Platform.CLIMATE))

    # Operating mode (required)
    schema[
        vol.Required(
            ConfKeys.OPERATING_MODE.value,
            default=resolved.operating_mode,
        )
    ] = selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=[m.value for m in OperatingMode],
            translation_key=SELECTOR_KEY_OPERATING_MODE,
            mode=selector.SelectSelectorMode.DROPDOWN,
        )
    )

    # Auto-disable on HVAC off (required, boolean)
    schema[
        vol.Required(
            ConfKeys.AUTO_DISABLE_ON_HVAC_OFF.value,
            default=resolved.auto_disable_on_hvac_off,
        )
    ] = selector.BooleanSelector()

    return vol.Schema(schema)


#
# _build_schema_step_2
#
def _build_schema_step_2(
    defaults: dict[str, Any],
    has_climate: bool,
) -> vol.Schema:
    """Build the voluptuous schema for step 2: Temperature Sensors & Target.

    Args:
        defaults: Current/default values keyed by ConfKeys string values.
        has_climate: Whether a climate entity was configured in step 1.

    Returns:
        Schema for the step 2 form.
    """

    resolved = resolve(defaults)
    schema: dict[vol.Marker, Any] = {}

    # Temperature sensor (optional when a climate entity provides current_temperature)
    schema[vol.Optional(ConfKeys.TEMP_SENSOR.value)] = selector.EntitySelector(
        selector.EntitySelectorConfig(
            domain=Platform.SENSOR,
            device_class=SensorDeviceClass.TEMPERATURE,
        )
    )

    # Target temperature mode
    mode_options = [TARGET_TEMP_MODE_INTERNAL, TARGET_TEMP_MODE_EXTERNAL]
    if has_climate:
        mode_options.append(TARGET_TEMP_MODE_CLIMATE)

    schema[
        vol.Required(
            ConfKeys.TARGET_TEMP_MODE.value,
            default=resolved.target_temp_mode,
        )
    ] = selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=mode_options,
            translation_key=SELECTOR_KEY_TARGET_TEMP_MODE,
            mode=selector.SelectSelectorMode.DROPDOWN,
        )
    )

    # Target temperature entity (relevant when mode = external)
    schema[vol.Optional(ConfKeys.TARGET_TEMP_ENTITY.value)] = selector.EntitySelector(selector.EntitySelectorConfig())

    # Note: target temperature (internal setpoint) is not in the options flow.
    # It is adjusted at runtime via the target_temp number entity, which handles
    # unit conversion (Celsius/Fahrenheit) correctly via device_class=TEMPERATURE.

    return vol.Schema(schema)


#
# _build_schema_step_3
#
def _build_schema_step_3(defaults: dict[str, Any]) -> vol.Schema:
    """Build the voluptuous schema for step 3: Output & Sensor Fault Mode.

    Args:
        defaults: Current/default values keyed by ConfKeys string values.

    Returns:
        Schema for the step 3 form.
    """

    resolved = resolve(defaults)
    schema: dict[vol.Marker, Any] = {}

    # Output entity (optional — input_number or number)
    schema[vol.Optional(ConfKeys.OUTPUT_ENTITY.value)] = selector.EntitySelector(
        selector.EntitySelectorConfig(domain=DOMAINS_OUTPUT_ENTITY)
    )

    # Sensor fault mode
    schema[
        vol.Required(
            ConfKeys.SENSOR_FAULT_MODE.value,
            default=resolved.sensor_fault_mode,
        )
    ] = selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=[m.value for m in SensorFaultMode],
            translation_key=SELECTOR_KEY_SENSOR_FAULT_MODE,
            mode=selector.SelectSelectorMode.DROPDOWN,
        )
    )

    # Integral term startup mode
    schema[
        vol.Required(
            ConfKeys.ITERM_STARTUP_MODE.value,
            default=resolved.iterm_startup_mode,
        )
    ] = selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=[m.value for m in ITermStartupMode],
            translation_key=SELECTOR_KEY_ITERM_STARTUP_MODE,
            mode=selector.SelectSelectorMode.DROPDOWN,
        )
    )

    # Integral term startup value (used when mode is 'last' as fallback, or 'fixed')
    schema[
        vol.Required(
            ConfKeys.ITERM_STARTUP_VALUE.value,
            default=resolved.iterm_startup_value,
        )
    ] = selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=0.0,
            max=100.0,
            step=0.1,
            unit_of_measurement="%",
            mode=selector.NumberSelectorMode.BOX,
        )
    )

    return vol.Schema(schema)


# ===========================================================================
# Validation helpers
# ===========================================================================


#
# _validate_step_1
#
def _validate_step_1(user_input: dict[str, Any]) -> dict[str, str]:
    """Validate step 1 input: climate entity and operating mode.

    Rules:
    - Operating mode 'heat_cool' requires a climate entity (to read hvac_action).

    Args:
        user_input: Form data submitted by the user.

    Returns:
        Dictionary of field-key to error-key pairs (empty if valid).
    """

    errors: dict[str, str] = {}

    climate = user_input.get(ConfKeys.CLIMATE_ENTITY.value, "")
    mode = user_input.get(ConfKeys.OPERATING_MODE.value, "")

    if mode == OperatingMode.HEAT_COOL and not climate:
        errors[ConfKeys.OPERATING_MODE.value] = ERROR_HEAT_COOL_REQUIRES_CLIMATE

    return errors


#
# _validate_step_2
#
def _validate_step_2(
    user_input: dict[str, Any],
    has_climate: bool,
) -> dict[str, str]:
    """Validate step 2 input: temperature sources and target.

    Rules:
    - At least one temperature source (temp sensor or climate entity).
    - Target temp mode 'climate' requires a climate entity.

    Args:
        user_input: Form data submitted by the user.
        has_climate: Whether a climate entity was configured in step 1.

    Returns:
        Dictionary of field-key to error-key pairs (empty if valid).
    """

    errors: dict[str, str] = {}

    temp_sensor = user_input.get(ConfKeys.TEMP_SENSOR.value, "")
    target_mode = user_input.get(ConfKeys.TARGET_TEMP_MODE.value, TARGET_TEMP_MODE_INTERNAL)

    # At least one temperature source must be configured
    if not temp_sensor and not has_climate:
        errors[ConfKeys.TEMP_SENSOR.value] = ERROR_NO_TEMP_SOURCE

    # Target temp mode 'climate' requires climate entity
    if target_mode == TARGET_TEMP_MODE_CLIMATE and not has_climate:
        errors[ConfKeys.TARGET_TEMP_MODE.value] = ERROR_CLIMATE_TARGET_REQUIRES_CLIMATE

    return errors


# ===========================================================================
# Config flow (initial setup)
# ===========================================================================


#
# FlowHandler
#
class FlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for the PI Thermostat integration.

    The config flow has no user-configurable fields. It creates the config
    entry with all defaults and prompts HA for the instance name.
    """

    # Schema version -- increment and implement async_migrate_entry on changes
    VERSION = 1

    # Explicit domain attribute for tests referencing FlowHandler.domain
    domain = DOMAIN

    #
    # async_step_user
    #
    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> config_entries.ConfigFlowResult:
        """Handle initial setup -- create entry with default config.

        Shows a welcome page with no input fields. When the user clicks
        submit, creates a config entry with empty data (all defaults apply).
        """

        if user_input is None:
            # Show welcome message with no input fields
            return self.async_show_form(
                step_id="user",
                data_schema=vol.Schema({}),
                description_placeholders={"docs_url": DOCS_URL},
            )

        # User clicked submit -- create entry with empty config
        return self.async_create_entry(
            title=INTEGRATION_NAME,
            data={},
        )

    #
    # async_get_options_flow
    #
    @staticmethod
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Create the options flow."""

        return OptionsFlowHandler(config_entry)


# ===========================================================================
# Options flow (post-setup configuration)
# ===========================================================================


#
# OptionsFlowHandler
#
class OptionsFlowHandler(config_entries.OptionsFlow):
    """Handle post-setup configuration for the PI Thermostat integration.

    Three-step wizard:
      1. Climate Entity & Operating Mode
      2. Temperature Sensors & Target
      3. Output & Sensor Fault Mode
    """

    #
    # __init__
    #
    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow.

        Avoid assigning to OptionsFlow.config_entry directly to prevent
        frame-helper warnings in tests; keep a private reference instead.
        """

        self._config_entry = config_entry
        self._config_data: dict[str, Any] = {}
        self._logger = Log(entry_id=config_entry.entry_id)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    #
    # _current_settings
    #
    def _current_settings(self) -> dict[str, Any]:
        """Return current option values as a plain dict."""

        return dict(self._config_entry.options) if self._config_entry.options else {}

    #
    # _has_climate
    #
    def _has_climate(self) -> bool:
        """Check if a climate entity is configured (from flow data or existing settings)."""

        climate = self._config_data.get(
            ConfKeys.CLIMATE_ENTITY.value,
            self._current_settings().get(ConfKeys.CLIMATE_ENTITY.value, ""),
        )
        return bool(climate)

    #
    # _merged_defaults
    #
    def _merged_defaults(self) -> dict[str, Any]:
        """Merge current settings with data collected in earlier steps."""

        return {**self._current_settings(), **self._config_data}

    #
    # _finalize_and_save
    #
    def _finalize_and_save(self) -> config_entries.ConfigFlowResult:
        """Merge flow data with current settings, clean up, and persist.

        Empty-string values (cleared optional entity selectors) are stripped
        so the options dict stays tidy. The saved options trigger a reload
        of the integration via the update listener registered in __init__.py.

        Returns:
            ConfigFlowResult that completes the options flow.
        """

        merged = self._merged_defaults()

        # Strip empty-string values (cleared optional fields)
        cleaned = {k: v for k, v in merged.items() if v != ""}

        self._logger.info(f"Options flow completed. Saving configuration: {cleaned}")
        return self.async_create_entry(title="", data=cleaned)

    # ------------------------------------------------------------------
    # Steps
    # ------------------------------------------------------------------

    #
    # async_step_init
    #
    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> config_entries.ConfigFlowResult:
        """Step 1: Climate Entity & Operating Mode."""

        defaults = self._merged_defaults()

        schema = _build_schema_step_1(defaults)

        if user_input is None:
            return self.async_show_form(
                step_id="init",
                data_schema=self.add_suggested_values_to_schema(schema, defaults),
            )

        # Validate
        errors = _validate_step_1(user_input)
        if errors:
            return self.async_show_form(
                step_id="init",
                data_schema=self.add_suggested_values_to_schema(schema, user_input),
                errors=errors,
            )

        self._logger.debug(f"Options flow step 1 input: {user_input}")
        self._config_data.update(user_input)
        return await self.async_step_2()

    #
    # async_step_2
    #
    async def async_step_2(self, user_input: dict[str, Any] | None = None) -> config_entries.ConfigFlowResult:
        """Step 2: Temperature Sensors & Target."""

        has_climate = self._has_climate()
        defaults = self._merged_defaults()
        schema = _build_schema_step_2(defaults, has_climate)

        if user_input is None:
            return self.async_show_form(
                step_id="2",
                data_schema=self.add_suggested_values_to_schema(schema, defaults),
            )

        # Validate
        errors = _validate_step_2(user_input, has_climate)
        if errors:
            return self.async_show_form(
                step_id="2",
                data_schema=self.add_suggested_values_to_schema(schema, user_input),
                errors=errors,
            )

        self._logger.debug(f"Options flow step 2 input: {user_input}")
        self._config_data.update(user_input)
        return await self.async_step_3()

    #
    # async_step_3
    #
    async def async_step_3(self, user_input: dict[str, Any] | None = None) -> config_entries.ConfigFlowResult:
        """Step 3: Output & Sensor Fault Mode."""

        defaults = self._merged_defaults()
        schema = _build_schema_step_3(defaults)

        if user_input is None:
            return self.async_show_form(
                step_id="3",
                data_schema=self.add_suggested_values_to_schema(schema, defaults),
            )

        self._logger.debug(f"Options flow step 3 input: {user_input}")
        self._config_data.update(user_input)
        return self._finalize_and_save()
