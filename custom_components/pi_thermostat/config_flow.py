"""Config flow and options flow for PI Thermostat & CCA Control integration.

The config flow is minimal: it creates an entry with default settings and no
user-configurable fields. All real configuration happens in the options flow.

The options flow begins with controller-mode selection, then continues with the
PI or CCA configuration steps required for that mode.

PI tuning parameters are adjusted at runtime via number entities rather than
the options flow.
"""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.const import Platform
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import selector

from .config import ConfKeys, resolve
from .const import (
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
from .log import Log

# ---------------------------------------------------------------------------
# Selector translation keys (used by SelectSelector to look up labels)
# ---------------------------------------------------------------------------

SELECTOR_KEY_OPERATING_MODE: str = "operating_mode"
SELECTOR_KEY_TARGET_TEMP_MODE: str = "target_temp_mode"
SELECTOR_KEY_SENSOR_FAULT_MODE: str = "sensor_fault_mode"
SELECTOR_KEY_ITERM_STARTUP_MODE: str = "iterm_startup_mode"
SELECTOR_KEY_CONTROL_MODE: str = "control_mode"
SELECTOR_KEY_CCA_FORECAST_UNAVAILABLE_MODE: str = "cca_forecast_unavailable_mode"

# ---------------------------------------------------------------------------
# Documentation URL shown in the config flow welcome page
# ---------------------------------------------------------------------------

DOCS_URL: str = "https://ha-pi-thermostat.helgeklein.com/"

# ---------------------------------------------------------------------------
# Entity selector domains
# ---------------------------------------------------------------------------

CCA_ENABLE_ENTITY_DOMAINS: tuple[str, ...] = (
    "binary_sensor",
    "input_boolean",
    "switch",
)

# ===========================================================================
# Schema builders
# ===========================================================================


#
# _build_schema_step_mode
#
def _build_schema_step_mode(defaults: dict[str, Any]) -> vol.Schema:
    """Build the schema for controller-mode selection."""

    resolved = resolve(defaults)
    schema: dict[vol.Marker, Any] = {}

    schema[
        vol.Required(
            ConfKeys.CONTROL_MODE.value,
            default=resolved.control_mode,
        )
    ] = selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=[m.value for m in ControlMode],
            translation_key=SELECTOR_KEY_CONTROL_MODE,
            mode=selector.SelectSelectorMode.DROPDOWN,
        )
    )

    return vol.Schema(schema)


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

    # Target temperature mode — default to CLIMATE when a climate entity is configured
    mode_options = [TargetTempMode.INTERNAL, TargetTempMode.EXTERNAL]
    if has_climate:
        mode_options.append(TargetTempMode.CLIMATE)

    default_mode = resolved.target_temp_mode
    if has_climate and ConfKeys.TARGET_TEMP_MODE.value not in defaults:
        # When a climate entity is configured and the user hasn't explicitly
        # saved a target-temp-mode preference yet, default to CLIMATE.
        default_mode = TargetTempMode.CLIMATE

    schema[
        vol.Required(
            ConfKeys.TARGET_TEMP_MODE.value,
            default=default_mode,
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
    """Build the voluptuous schema for step 3: Sensor Fault & Startup Mode.

    Args:
        defaults: Current/default values keyed by ConfKeys string values.

    Returns:
        Schema for the step 3 form.
    """

    resolved = resolve(defaults)
    schema: dict[vol.Marker, Any] = {}

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


#
# _build_schema_step_cca_sources
#
def _build_schema_step_cca_sources(defaults: dict[str, Any]) -> vol.Schema:
    """Build the schema for CCA data-source configuration."""

    resolved = resolve(defaults)
    schema: dict[vol.Marker, Any] = {}

    schema[
        vol.Required(
            ConfKeys.CCA_COOLING_ENABLE_ENTITY.value,
            default=resolved.cca_cooling_enable_entity,
        )
    ] = selector.EntitySelector(selector.EntitySelectorConfig(domain=list(CCA_ENABLE_ENTITY_DOMAINS)))

    schema[
        vol.Required(
            ConfKeys.CCA_COOLING_ENABLE_ON.value,
            default=resolved.cca_cooling_enable_on,
        )
    ] = selector.BooleanSelector()

    schema[
        vol.Required(
            ConfKeys.CCA_WEATHER_ENTITY.value,
            default=resolved.cca_weather_entity,
        )
    ] = selector.EntitySelector(selector.EntitySelectorConfig(domain=Platform.WEATHER))

    schema[
        vol.Required(
            ConfKeys.CCA_FORECAST_HORIZON_DAYS.value,
            default=resolved.cca_forecast_horizon_days,
        )
    ] = selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=1.0,
            max=7.0,
            step=1.0,
            mode=selector.NumberSelectorMode.BOX,
        )
    )

    schema[
        vol.Required(
            ConfKeys.CCA_FORECAST_UNAVAILABLE_MODE.value,
            default=resolved.cca_forecast_unavailable_mode,
        )
    ] = selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=[m.value for m in CCAForecastUnavailableMode],
            translation_key=SELECTOR_KEY_CCA_FORECAST_UNAVAILABLE_MODE,
            mode=selector.SelectSelectorMode.DROPDOWN,
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
    target_mode = user_input.get(ConfKeys.TARGET_TEMP_MODE.value, TargetTempMode.INTERNAL)

    # At least one temperature source must be configured
    if not temp_sensor and not has_climate:
        errors[ConfKeys.TEMP_SENSOR.value] = ERROR_NO_TEMP_SOURCE

    # Target temp mode 'climate' requires climate entity
    if target_mode == TargetTempMode.CLIMATE and not has_climate:
        errors[ConfKeys.TARGET_TEMP_MODE.value] = ERROR_CLIMATE_TARGET_REQUIRES_CLIMATE

    return errors


#
# _validate_step_cca_sources
#
async def _validate_step_cca_sources(
    hass: Any,
    user_input: dict[str, Any],
) -> dict[str, str]:
    """Validate the CCA data-source step."""

    errors: dict[str, str] = {}

    cooling_enable_entity = user_input.get(ConfKeys.CCA_COOLING_ENABLE_ENTITY.value, "")
    weather_entity = user_input.get(ConfKeys.CCA_WEATHER_ENTITY.value, "")

    if not cooling_enable_entity:
        errors[ConfKeys.CCA_COOLING_ENABLE_ENTITY.value] = ERROR_CCA_COOLING_ENABLE_REQUIRED

    if not weather_entity:
        errors[ConfKeys.CCA_WEATHER_ENTITY.value] = ERROR_CCA_WEATHER_REQUIRED
        return errors

    from .ha_interface import HomeAssistantInterface
    from .log import Log

    ha_interface = HomeAssistantInterface(hass, Log())

    try:
        await ha_interface.async_validate_daily_forecast_support(weather_entity)
    except HomeAssistantError:
        errors[ConfKeys.CCA_WEATHER_ENTITY.value] = ERROR_CCA_WEATHER_UNSUPPORTED

    return errors


# ===========================================================================
# Config flow (initial setup)
# ===========================================================================


#
# FlowHandler
#
class FlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for the PI Thermostat & CCA Control integration.

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
    """Handle post-setup configuration for the PI Thermostat & CCA Control integration.

    Mode-aware wizard:
        - PI path: mode -> climate -> temperature -> fault/startup
        - CCA path: mode -> data sources
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
    # _control_mode
    #
    def _control_mode(self) -> str:
        """Return the selected control mode from flow data or saved settings."""

        return str(
            self._config_data.get(
                ConfKeys.CONTROL_MODE.value,
                self._current_settings().get(ConfKeys.CONTROL_MODE.value, ControlMode.PI),
            )
        )

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
        """Step 1: controller mode."""

        defaults = self._merged_defaults()

        schema = _build_schema_step_mode(defaults)

        if user_input is None:
            return self.async_show_form(
                step_id="init",
                data_schema=self.add_suggested_values_to_schema(schema, defaults),
                last_step=False,
            )

        self._logger.debug(f"Options flow step 1 input: {user_input}")
        self._config_data.update(user_input)
        if self._control_mode() == ControlMode.CCA:
            return await self.async_step_cca_sources()
        return await self.async_step_2()

    #
    # async_step_2
    #
    async def async_step_2(self, user_input: dict[str, Any] | None = None) -> config_entries.ConfigFlowResult:
        """Step 2: Climate Entity & Operating Mode."""

        defaults = self._merged_defaults()
        schema = _build_schema_step_1(defaults)

        if user_input is None:
            return self.async_show_form(
                step_id="2",
                data_schema=self.add_suggested_values_to_schema(schema, defaults),
                last_step=False,
            )

        # Validate
        errors = _validate_step_1(user_input)
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
        """Step 3: Temperature Sensors & Target."""

        has_climate = self._has_climate()
        defaults = self._merged_defaults()
        schema = _build_schema_step_2(defaults, has_climate)

        if user_input is None:
            return self.async_show_form(
                step_id="3",
                data_schema=self.add_suggested_values_to_schema(schema, defaults),
                last_step=False,
            )

        errors = _validate_step_2(user_input, has_climate)
        if errors:
            return self.async_show_form(
                step_id="3",
                data_schema=self.add_suggested_values_to_schema(schema, user_input),
                errors=errors,
            )

        self._logger.debug(f"Options flow step 3 input: {user_input}")
        self._config_data.update(user_input)
        return await self.async_step_4()

    #
    # async_step_4
    #
    async def async_step_4(self, user_input: dict[str, Any] | None = None) -> config_entries.ConfigFlowResult:
        """Step 4: Sensor Fault & Startup Mode."""

        defaults = self._merged_defaults()
        schema = _build_schema_step_3(defaults)

        if user_input is None:
            return self.async_show_form(
                step_id="4",
                data_schema=self.add_suggested_values_to_schema(schema, defaults),
                last_step=True,
            )

        self._logger.debug(f"Options flow step 4 input: {user_input}")
        self._config_data.update(user_input)
        return self._finalize_and_save()

    #
    # async_step_cca_sources
    #
    async def async_step_cca_sources(self, user_input: dict[str, Any] | None = None) -> config_entries.ConfigFlowResult:
        """Step 2 of the CCA path: data sources."""

        defaults = self._merged_defaults()
        schema = _build_schema_step_cca_sources(defaults)

        if user_input is None:
            return self.async_show_form(
                step_id="cca_sources",
                data_schema=self.add_suggested_values_to_schema(schema, defaults),
                last_step=True,
            )

        errors = await _validate_step_cca_sources(self.hass, user_input)
        if errors:
            return self.async_show_form(
                step_id="cca_sources",
                data_schema=self.add_suggested_values_to_schema(schema, user_input),
                errors=errors,
                last_step=True,
            )

        self._logger.debug(f"Options flow CCA sources input: {user_input}")
        self._config_data.update(user_input)
        return self._finalize_and_save()
