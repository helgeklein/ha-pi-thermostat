"""Constants for pi_thermostat.

Central definitions for domain identity, default values, entity keys, and enums.
All magic numbers and strings used across the integration are defined here.
"""

from __future__ import annotations

from enum import Enum, StrEnum
from typing import TYPE_CHECKING, Final

# For static type checking only
if TYPE_CHECKING:
    from .log import Log

# ---------------------------------------------------------------------------
# Module-level logger
# ---------------------------------------------------------------------------

# Module-level logger for the integration.
# This is an instance of the custom Log class which wraps Python's standard logger.
# Without an entry_id, log messages have no prefix.
# With an entry_id, messages are prefixed with [xxxxx] to identify the instance.
#
# Note: Imported lazily to avoid circular imports.
#       Instantiated at module load time by _init_logger().
LOGGER: Log


#
# _init_logger
#
def _init_logger() -> None:
    """Initialize the module-level LOGGER. Called once at module load time."""

    global LOGGER  # noqa: PLW0603
    try:
        from .log import Log

        LOGGER = Log()
    except ImportError:
        # Fallback for when module is loaded outside package context (e.g., CI tests)
        # Import log.py directly to avoid triggering __init__.py which needs homeassistant
        import importlib.util
        from pathlib import Path

        log_path = Path(__file__).parent / "log.py"
        spec = importlib.util.spec_from_file_location("log", log_path)
        if spec and spec.loader:
            log_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(log_module)
            LOGGER = log_module.Log()
        else:
            raise ImportError("Could not load log.py")


# ---------------------------------------------------------------------------
# Log severity
# ---------------------------------------------------------------------------


#
# LogSeverity
#
class LogSeverity(Enum):
    """Log severity levels for structured logging."""

    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


# ---------------------------------------------------------------------------
# Domain identity
# ---------------------------------------------------------------------------

DOMAIN: Final[str] = "pi_thermostat"
INTEGRATION_NAME: Final[str] = "PI Thermostat"

# Home Assistant string literals
HA_OPTIONS: Final[str] = "options"

# ---------------------------------------------------------------------------
# Coordinator defaults
# ---------------------------------------------------------------------------

UPDATE_INTERVAL_DEFAULT_SECONDS: Final[int] = 60

# ---------------------------------------------------------------------------
# PI controller defaults (HVAC-standard units)
# ---------------------------------------------------------------------------

DEFAULT_PROP_BAND: Final[float] = 4.0  # Proportional band in Kelvin
DEFAULT_INT_TIME: Final[float] = 120.0  # Integral time (reset time) in minutes
DEFAULT_OUTPUT_MIN: Final[float] = 0.0  # Minimum output %
DEFAULT_OUTPUT_MAX: Final[float] = 100.0  # Maximum output %

# ---------------------------------------------------------------------------
# Entity keys — sensors (read-only, from coordinator data)
# ---------------------------------------------------------------------------

SENSOR_KEY_OUTPUT: Final[str] = "output"  # PI output percentage
SENSOR_KEY_ERROR: Final[str] = "error"  # Current error (target − actual)
SENSOR_KEY_P_TERM: Final[str] = "p_term"  # Proportional component
SENSOR_KEY_I_TERM: Final[str] = "i_term"  # Integral component (also persisted)

# ---------------------------------------------------------------------------
# Entity keys — number entities (writable, runtime-configurable)
# ---------------------------------------------------------------------------

NUMBER_KEY_PROP_BAND: Final[str] = "proportional_band"
NUMBER_KEY_INT_TIME: Final[str] = "integral_time"
NUMBER_KEY_TARGET_TEMP: Final[str] = "target_temp"
NUMBER_KEY_OUTPUT_MIN: Final[str] = "output_min"
NUMBER_KEY_OUTPUT_MAX: Final[str] = "output_max"
NUMBER_KEY_UPDATE_INTERVAL: Final[str] = "update_interval"

# ---------------------------------------------------------------------------
# Entity keys — switches
# ---------------------------------------------------------------------------

SWITCH_KEY_ENABLED: Final[str] = "enabled"

# ---------------------------------------------------------------------------
# Entity keys — binary sensors
# ---------------------------------------------------------------------------

BINARY_SENSOR_KEY_ACTIVE: Final[str] = "active"

# ---------------------------------------------------------------------------
# Operating mode enum
# ---------------------------------------------------------------------------


#
# OperatingMode
#
class OperatingMode(StrEnum):
    """How the controller determines heating vs. cooling direction."""

    HEAT_COOL = "heat_cool"  # Auto: read mode from a climate entity
    HEAT = "heat"  # Heating only
    COOL = "cool"  # Cooling only


# ---------------------------------------------------------------------------
# Target temperature mode constants
# ---------------------------------------------------------------------------

TARGET_TEMP_MODE_INTERNAL: Final[str] = "internal"
TARGET_TEMP_MODE_EXTERNAL: Final[str] = "external"
TARGET_TEMP_MODE_CLIMATE: Final[str] = "climate"

# ---------------------------------------------------------------------------
# Sensor fault behavior enum
# ---------------------------------------------------------------------------


#
# SensorFaultMode
#
class SensorFaultMode(StrEnum):
    """Behavior when the temperature sensor becomes unavailable."""

    SHUTDOWN = "shutdown"  # Set output to 0% immediately
    HOLD = "hold"  # Hold last output for grace period, then shutdown


# ---------------------------------------------------------------------------
# Safety
# ---------------------------------------------------------------------------

SENSOR_FAULT_GRACE_PERIOD_SECONDS: Final[int] = 300  # 5 min before shutdown in HOLD mode

# ---------------------------------------------------------------------------
# Options flow error translation keys
# ---------------------------------------------------------------------------

ERROR_NO_TEMP_SOURCE: Final[str] = "no_temp_source"
ERROR_HEAT_COOL_REQUIRES_CLIMATE: Final[str] = "heat_cool_requires_climate"
ERROR_CLIMATE_TARGET_REQUIRES_CLIMATE: Final[str] = "climate_target_requires_climate"
ERROR_PROP_BAND_POSITIVE: Final[str] = "prop_band_positive"
ERROR_INT_TIME_POSITIVE: Final[str] = "int_time_positive"
ERROR_OUTPUT_MIN_LT_MAX: Final[str] = "output_min_lt_max"

# ---------------------------------------------------------------------------
# Module initialization
# ---------------------------------------------------------------------------

_init_logger()
