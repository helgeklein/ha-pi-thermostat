"""Settings registry and resolution for pi_thermostat.

This module defines a typo-safe enum of setting keys, a registry of specs with
defaults and coercion, and helpers to resolve effective settings from a
ConfigEntry (options → defaults).
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from enum import StrEnum
from typing import Any, Callable, Generic, Mapping, TypeVar

from custom_components.pi_thermostat.const import (
    CCA_TUNING_MAX,
    CCA_TUNING_MIN,
    DEFAULT_CCA_CHARGE_GAIN,
    DEFAULT_CCA_CHARGE_TARGET_SCALE,
    DEFAULT_CCA_COOLING_ENABLE_ON,
    DEFAULT_CCA_DISCHARGE_GAIN,
    DEFAULT_CCA_FORECAST_HORIZON_DAYS,
    DEFAULT_CCA_FORECAST_RESPONSE_STRENGTH,
    DEFAULT_CCA_HOT_DAY_THRESHOLD,
    DEFAULT_CCA_MANUAL_OUTPUT,
    DEFAULT_CCA_OUTPUT_MAX,
    DEFAULT_CCA_OUTPUT_MIN,
    DEFAULT_CCA_OUTPUT_STEP_LIMIT,
    DEFAULT_CCA_THERMAL_STORAGE_PERSISTENCE,
    DEFAULT_CCA_UPDATE_INTERVAL_MINUTES,
    DEFAULT_CCA_WARM_NIGHT_THRESHOLD,
    DEFAULT_INT_TIME,
    DEFAULT_ITERM_STARTUP_VALUE,
    DEFAULT_OUTPUT_MAX,
    DEFAULT_OUTPUT_MIN,
    DEFAULT_PROP_BAND,
    HA_OPTIONS,
    UPDATE_INTERVAL_DEFAULT_SECONDS,
    CCAForecastUnavailableMode,
    ControlMode,
    ITermStartupMode,
    OperatingMode,
    SensorFaultMode,
    TargetTempMode,
)

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class _ConfSpec(Generic[T]):
    """Metadata for a configuration setting.

    Attributes:
    - default: The default value for the setting.
    - converter: A callable that converts a raw value to the desired type T.
    - runtime_configurable: Whether this setting can be changed at runtime via an entity
                           (switch, number) without requiring a full integration reload.
                           Settings with corresponding control entities should be True.
    """

    default: T
    converter: Callable[[Any], T]
    runtime_configurable: bool = False

    def __post_init__(self) -> None:
        """Validate that default is not None."""

        # Disallow None default values to ensure ResolvedConfig fields are always concrete.
        if self.default is None:
            raise ValueError("_ConfSpec.default must not be None")


#
# ConfKeys
#
class ConfKeys(StrEnum):
    """Configuration keys for the integration's settings.

    Each key corresponds to a setting that can be configured via options.
    """

    ENABLED = "enabled"
    CLIMATE_ENTITY = "climate_entity"
    TEMP_SENSOR = "temp_sensor"
    TARGET_TEMP_MODE = "target_temp_mode"
    TARGET_TEMP_ENTITY = "target_temp_entity"
    TARGET_TEMP = "target_temp"
    OPERATING_MODE = "operating_mode"
    AUTO_DISABLE_ON_HVAC_OFF = "auto_disable_on_hvac_off"
    PROPORTIONAL_BAND = "proportional_band"
    INTEGRAL_TIME = "integral_time"
    OUTPUT_MIN = "output_min"
    OUTPUT_MAX = "output_max"
    UPDATE_INTERVAL = "update_interval"
    SENSOR_FAULT_MODE = "sensor_fault_mode"
    ITERM_STARTUP_MODE = "iterm_startup_mode"
    ITERM_STARTUP_VALUE = "iterm_startup_value"
    CONTROL_MODE = "control_mode"
    CCA_COOLING_ENABLE_ENTITY = "cca_cooling_enable_entity"
    CCA_COOLING_ENABLE_ON = "cca_cooling_enable_on"
    CCA_WEATHER_ENTITY = "cca_weather_entity"
    CCA_FORECAST_HORIZON_DAYS = "cca_forecast_horizon_days"
    CCA_FORECAST_UNAVAILABLE_MODE = "cca_forecast_unavailable_mode"
    CCA_UPDATE_INTERVAL_MINUTES = "cca_update_interval_minutes"
    CCA_MANUAL_OVERRIDE_ENABLED = "cca_manual_override_enabled"
    CCA_MANUAL_OUTPUT = "cca_manual_output"
    CCA_HOT_DAY_THRESHOLD = "cca_hot_day_threshold"
    CCA_WARM_NIGHT_THRESHOLD = "cca_warm_night_threshold"
    CCA_OUTPUT_MIN = "cca_output_min"
    CCA_OUTPUT_MAX = "cca_output_max"
    CCA_FORECAST_RESPONSE_STRENGTH = "cca_forecast_response_strength"
    CCA_THERMAL_STORAGE_PERSISTENCE = "cca_thermal_storage_persistence"
    CCA_OUTPUT_STEP_LIMIT = "cca_output_step_limit"
    CCA_CHARGE_TARGET_SCALE = "cca_charge_target_scale"


class _Converters:
    """Coercion helpers used by _ConfSpec."""

    @staticmethod
    def to_bool(v: Any) -> bool:
        """Convert various boolean representations to bool.

        Handles native bools, integers, and common string representations
        (true/false, yes/no, on/off, 1/0).
        """

        if isinstance(v, bool):
            return v
        if isinstance(v, str):
            normalized = v.lower().strip()
            if normalized in ("true", "yes", "on", "1"):
                return True
            if normalized in ("false", "no", "off", "0"):
                return False
        return bool(v)

    @staticmethod
    def to_int(v: Any) -> int:
        """Convert to int."""

        return int(v)

    @staticmethod
    def to_float(v: Any) -> float:
        """Convert to float."""

        return float(v)

    @staticmethod
    def to_cca_tuning_value(v: Any) -> float:
        """Validate a CCA tuning slider value."""

        value = float(v)
        if value < CCA_TUNING_MIN or value > CCA_TUNING_MAX:
            raise ValueError(f"CCA tuning value out of range: {v}")
        return value

    @staticmethod
    def to_str(v: Any) -> str:
        """Convert to str."""

        return str(v)

    @staticmethod
    def to_cca_forecast_unavailable_mode(v: Any) -> str:
        """Validate supported CCA forecast fallback values."""

        normalized = str(v).strip()
        if normalized in {CCAForecastUnavailableMode.HOLD, CCAForecastUnavailableMode.SHUTDOWN}:
            return normalized
        raise ValueError(f"Unsupported CCA forecast fallback mode: {v}")


# Central registry of settings with defaults and coercion (type conversion).
# This is the single source of truth for all settings keys and their types.
CONF_SPECS: dict[ConfKeys, _ConfSpec[Any]] = {
    ConfKeys.ENABLED: _ConfSpec(
        default=True,
        converter=_Converters.to_bool,
        runtime_configurable=True,
    ),
    ConfKeys.CLIMATE_ENTITY: _ConfSpec(
        default="",
        converter=_Converters.to_str,
    ),
    ConfKeys.TEMP_SENSOR: _ConfSpec(
        default="",
        converter=_Converters.to_str,
    ),
    ConfKeys.TARGET_TEMP_MODE: _ConfSpec(
        default=TargetTempMode.INTERNAL,
        converter=_Converters.to_str,
    ),
    ConfKeys.TARGET_TEMP_ENTITY: _ConfSpec(
        default="",
        converter=_Converters.to_str,
    ),
    ConfKeys.TARGET_TEMP: _ConfSpec(
        default=20.0,
        converter=_Converters.to_float,
        runtime_configurable=True,
    ),
    ConfKeys.OPERATING_MODE: _ConfSpec(
        default=OperatingMode.HEAT_COOL,
        converter=_Converters.to_str,
    ),
    ConfKeys.AUTO_DISABLE_ON_HVAC_OFF: _ConfSpec(
        default=True,
        converter=_Converters.to_bool,
        runtime_configurable=True,
    ),
    ConfKeys.PROPORTIONAL_BAND: _ConfSpec(
        default=DEFAULT_PROP_BAND,
        converter=_Converters.to_float,
        runtime_configurable=True,
    ),
    ConfKeys.INTEGRAL_TIME: _ConfSpec(
        default=DEFAULT_INT_TIME,
        converter=_Converters.to_float,
        runtime_configurable=True,
    ),
    ConfKeys.OUTPUT_MIN: _ConfSpec(
        default=DEFAULT_OUTPUT_MIN,
        converter=_Converters.to_float,
        runtime_configurable=True,
    ),
    ConfKeys.OUTPUT_MAX: _ConfSpec(
        default=DEFAULT_OUTPUT_MAX,
        converter=_Converters.to_float,
        runtime_configurable=True,
    ),
    ConfKeys.UPDATE_INTERVAL: _ConfSpec(
        default=UPDATE_INTERVAL_DEFAULT_SECONDS,
        converter=_Converters.to_int,
        runtime_configurable=True,
    ),
    ConfKeys.SENSOR_FAULT_MODE: _ConfSpec(
        default=SensorFaultMode.HOLD,
        converter=_Converters.to_str,
    ),
    ConfKeys.ITERM_STARTUP_MODE: _ConfSpec(
        default=ITermStartupMode.LAST,
        converter=_Converters.to_str,
    ),
    ConfKeys.ITERM_STARTUP_VALUE: _ConfSpec(
        default=DEFAULT_ITERM_STARTUP_VALUE,
        converter=_Converters.to_float,
    ),
    ConfKeys.CONTROL_MODE: _ConfSpec(
        default=ControlMode.PI,
        converter=_Converters.to_str,
    ),
    ConfKeys.CCA_COOLING_ENABLE_ENTITY: _ConfSpec(
        default="",
        converter=_Converters.to_str,
    ),
    ConfKeys.CCA_COOLING_ENABLE_ON: _ConfSpec(
        default=DEFAULT_CCA_COOLING_ENABLE_ON,
        converter=_Converters.to_bool,
    ),
    ConfKeys.CCA_WEATHER_ENTITY: _ConfSpec(
        default="",
        converter=_Converters.to_str,
    ),
    ConfKeys.CCA_FORECAST_HORIZON_DAYS: _ConfSpec(
        default=DEFAULT_CCA_FORECAST_HORIZON_DAYS,
        converter=_Converters.to_int,
    ),
    ConfKeys.CCA_FORECAST_UNAVAILABLE_MODE: _ConfSpec(
        default=CCAForecastUnavailableMode.HOLD,
        converter=_Converters.to_cca_forecast_unavailable_mode,
    ),
    ConfKeys.CCA_UPDATE_INTERVAL_MINUTES: _ConfSpec(
        default=DEFAULT_CCA_UPDATE_INTERVAL_MINUTES,
        converter=_Converters.to_int,
        runtime_configurable=True,
    ),
    ConfKeys.CCA_MANUAL_OVERRIDE_ENABLED: _ConfSpec(
        default=False,
        converter=_Converters.to_bool,
        runtime_configurable=True,
    ),
    ConfKeys.CCA_MANUAL_OUTPUT: _ConfSpec(
        default=DEFAULT_CCA_MANUAL_OUTPUT,
        converter=_Converters.to_float,
        runtime_configurable=True,
    ),
    ConfKeys.CCA_HOT_DAY_THRESHOLD: _ConfSpec(
        default=DEFAULT_CCA_HOT_DAY_THRESHOLD,
        converter=_Converters.to_float,
        runtime_configurable=True,
    ),
    ConfKeys.CCA_WARM_NIGHT_THRESHOLD: _ConfSpec(
        default=DEFAULT_CCA_WARM_NIGHT_THRESHOLD,
        converter=_Converters.to_float,
        runtime_configurable=True,
    ),
    ConfKeys.CCA_OUTPUT_MIN: _ConfSpec(
        default=DEFAULT_CCA_OUTPUT_MIN,
        converter=_Converters.to_float,
        runtime_configurable=True,
    ),
    ConfKeys.CCA_OUTPUT_MAX: _ConfSpec(
        default=DEFAULT_CCA_OUTPUT_MAX,
        converter=_Converters.to_float,
        runtime_configurable=True,
    ),
    ConfKeys.CCA_FORECAST_RESPONSE_STRENGTH: _ConfSpec(
        default=DEFAULT_CCA_FORECAST_RESPONSE_STRENGTH,
        converter=_Converters.to_cca_tuning_value,
        runtime_configurable=True,
    ),
    ConfKeys.CCA_THERMAL_STORAGE_PERSISTENCE: _ConfSpec(
        default=DEFAULT_CCA_THERMAL_STORAGE_PERSISTENCE,
        converter=_Converters.to_cca_tuning_value,
        runtime_configurable=True,
    ),
    ConfKeys.CCA_OUTPUT_STEP_LIMIT: _ConfSpec(
        default=DEFAULT_CCA_OUTPUT_STEP_LIMIT,
        converter=_Converters.to_float,
        runtime_configurable=True,
    ),
    ConfKeys.CCA_CHARGE_TARGET_SCALE: _ConfSpec(
        default=DEFAULT_CCA_CHARGE_TARGET_SCALE,
        converter=_Converters.to_float,
        runtime_configurable=True,
    ),
}

# Public API of this module (keep helper class internal)
__all__ = [
    "ConfKeys",
    "CONF_SPECS",
    "ResolvedConfig",
    "get_runtime_configurable_keys",
    "resolve",
    "resolve_entry",
]


#
# get_runtime_configurable_keys
#
def get_runtime_configurable_keys() -> set[str]:
    """Return the set of configuration keys that can be changed at runtime.

    These keys have corresponding entities (switches, numbers) and
    changes to them only require a coordinator refresh, not a full reload.

    Returns:
        Set of configuration key strings that are runtime configurable.
    """

    return {key.value for key, spec in CONF_SPECS.items() if spec.runtime_configurable}


#
# ResolvedConfig
#
@dataclass(frozen=True, slots=True)
class ResolvedConfig:
    """Fully resolved configuration with typed fields.

    All values are guaranteed to be non-None and of the correct type.
    """

    enabled: bool
    climate_entity: str
    temp_sensor: str
    target_temp_mode: str
    target_temp_entity: str
    target_temp: float
    operating_mode: str
    auto_disable_on_hvac_off: bool
    proportional_band: float
    integral_time: float
    output_min: float
    output_max: float
    update_interval: int
    sensor_fault_mode: str
    iterm_startup_mode: str
    iterm_startup_value: float
    control_mode: str
    cca_cooling_enable_entity: str
    cca_cooling_enable_on: bool
    cca_weather_entity: str
    cca_forecast_horizon_days: int
    cca_forecast_unavailable_mode: str
    cca_update_interval_minutes: int
    cca_manual_override_enabled: bool
    cca_manual_output: float
    cca_hot_day_threshold: float
    cca_warm_night_threshold: float
    cca_output_min: float
    cca_output_max: float
    cca_forecast_response_strength: float
    cca_thermal_storage_persistence: float
    cca_charge_gain: float
    cca_discharge_gain: float
    cca_output_step_limit: float
    cca_charge_target_scale: float

    #
    # get
    #
    def get(self, key: ConfKeys) -> Any:
        """Generic access: ConfKeys values match dataclass field names."""

        return getattr(self, key.value)

    #
    # as_enum_dict
    #
    def as_enum_dict(self) -> dict[ConfKeys, Any]:
        """Build dict keyed by ConfKeys without hard-coded names."""

        return {k: getattr(self, k.value) for k in ConfKeys}


#
# resolve
#
def resolve(options: Mapping[str, Any] | None) -> ResolvedConfig:
    """Resolve settings from options → defaults using ConfKeys.

    Only shallow keys are considered. Performs type coercion via each spec's converter.
    """

    options = options or {}

    def _val(key: ConfKeys) -> Any:
        spec = CONF_SPECS[key]
        if key.value in options:
            raw = options[key.value]
        else:
            raw = spec.default
        try:
            return spec.converter(raw)
        except Exception:
            if key is ConfKeys.CCA_FORECAST_UNAVAILABLE_MODE and key.value in options:
                raise
            # Fallback safely to default if coercion fails
            return spec.converter(spec.default)

    # Build kwargs dynamically by iterating over ConfKeys, applying coercion
    converted: dict[str, Any] = {k.value: _val(k) for k in ConfKeys}

    response_scale = converted[ConfKeys.CCA_FORECAST_RESPONSE_STRENGTH.value] / 100.0
    persistence_scale = converted[ConfKeys.CCA_THERMAL_STORAGE_PERSISTENCE.value] / 100.0
    converted["cca_charge_gain"] = max(10.0, min(40.0, DEFAULT_CCA_CHARGE_GAIN / persistence_scale))
    converted["cca_discharge_gain"] = max(
        8.0,
        min(40.0, DEFAULT_CCA_DISCHARGE_GAIN * response_scale / persistence_scale),
    )

    # Filter strictly to ResolvedConfig fields and fail clearly if anything is missing
    field_names = {f.name for f in fields(ResolvedConfig)}
    missing_for_dc = field_names - converted.keys()
    if missing_for_dc:
        raise RuntimeError(f"Missing values for ResolvedConfig fields: {missing_for_dc}")

    values: dict[str, Any] = {name: converted[name] for name in field_names}
    return ResolvedConfig(**values)


#
# resolve_entry
#
def resolve_entry(entry: Any) -> ResolvedConfig:
    """Resolve settings directly from a ConfigEntry-like object.

    All user settings are stored in options. Accepts any object with 'options'
    attribute (works with test mocks).
    """

    opts = getattr(entry, HA_OPTIONS, None) or {}
    return resolve(opts)
