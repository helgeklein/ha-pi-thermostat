"""Runtime data types for pi_thermostat.

Defines the data structures used at runtime:
- CoordinatorData: output of each coordinator update cycle, consumed by entities.
- RuntimeData: stored on config_entry.runtime_data during the integration's lifetime.
- IntegrationConfigEntry: typed alias for ConfigEntry[RuntimeData].
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.loader import Integration

    from .coordinator import DataUpdateCoordinator


# Type safety: entry.runtime_data will be of type RuntimeData
type IntegrationConfigEntry = ConfigEntry[RuntimeData]


#
# CoordinatorData
#
@dataclass
class CoordinatorData:
    """Output of each coordinator update cycle.

    All sensor entities read their values from this structure.

    Attributes:
        output: PI output percentage (0–100).
        deviation: Target − current temperature (or current − target in cool mode).
        p_term: Proportional component of the PI output.
        i_term: Integral component of the PI output.
        current_temp: Current temperature reading from the sensor.
        target_temp: Active target temperature (setpoint).
        sensor_available: Whether the temperature sensor is available.
    """

    output: float
    deviation: float | None = None
    p_term: float | None = None
    i_term: float | None = None
    current_temp: float | None = None
    target_temp: float | None = None
    sensor_available: bool = True


#
# RuntimeData
#
@dataclass
class RuntimeData:
    """Data stored on config_entry.runtime_data during the integration's lifetime."""

    coordinator: DataUpdateCoordinator
    integration: Integration
    config: dict[str, Any]
