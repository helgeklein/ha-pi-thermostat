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
    DEFAULT_INT_TIME,
    DEFAULT_OUTPUT_MAX,
    DEFAULT_OUTPUT_MIN,
    DEFAULT_PROP_BAND,
    HA_OPTIONS,
    TARGET_TEMP_MODE_INTERNAL,
    UPDATE_INTERVAL_DEFAULT_SECONDS,
    OperatingMode,
    SensorFaultMode,
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
    OUTPUT_ENTITY = "output_entity"
    OUTPUT_MIN = "output_min"
    OUTPUT_MAX = "output_max"
    UPDATE_INTERVAL = "update_interval"
    SENSOR_FAULT_MODE = "sensor_fault_mode"


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
    def to_str(v: Any) -> str:
        """Convert to str."""

        return str(v)


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
        default=TARGET_TEMP_MODE_INTERNAL,
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
    ConfKeys.OUTPUT_ENTITY: _ConfSpec(
        default="",
        converter=_Converters.to_str,
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
        default=SensorFaultMode.SHUTDOWN,
        converter=_Converters.to_str,
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
    output_entity: str
    output_min: float
    output_max: float
    update_interval: int
    sensor_fault_mode: str

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
            # Fallback safely to default if coercion fails
            return spec.converter(spec.default)

    # Build kwargs dynamically by iterating over ConfKeys, applying coercion
    converted: dict[str, Any] = {k.value: _val(k) for k in ConfKeys}

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
