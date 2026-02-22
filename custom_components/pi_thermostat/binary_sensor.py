"""Binary sensor platform for pi_thermostat.

Provides a single read-only binary sensor:

- **active** — On when the PI controller's output is > 0 %.
  Useful for dashboard display and automations.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorEntityDescription,
)

from .const import BINARY_SENSOR_KEY_ACTIVE
from .entity import IntegrationEntity

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .coordinator import DataUpdateCoordinator
    from .data import IntegrationConfigEntry


# ---------------------------------------------------------------------------
# Binary sensor descriptions
# ---------------------------------------------------------------------------

BINARY_SENSOR_ACTIVE = BinarySensorEntityDescription(
    key=BINARY_SENSOR_KEY_ACTIVE,
    translation_key=BINARY_SENSOR_KEY_ACTIVE,
    icon="mdi:fire",
)


# ---------------------------------------------------------------------------
# Platform setup
# ---------------------------------------------------------------------------


#
# async_setup_entry
#
async def async_setup_entry(
    hass: HomeAssistant,  # noqa: ARG001
    entry: IntegrationConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create all binary sensor entities for a config entry."""

    coordinator = entry.runtime_data.coordinator

    async_add_entities(
        [
            ActiveBinarySensor(coordinator),
        ]
    )


# ---------------------------------------------------------------------------
# Binary sensor entity class
# ---------------------------------------------------------------------------


#
# ActiveBinarySensor
#
class ActiveBinarySensor(IntegrationEntity, BinarySensorEntity):  # pyright: ignore[reportIncompatibleVariableOverride]
    """Binary sensor that is on when the PI controller output is > 0 %.

    Reads ``controller_active`` from ``CoordinatorData``.
    """

    #
    # __init__
    #
    def __init__(self, coordinator: DataUpdateCoordinator) -> None:
        """Initialize the active binary sensor.

        Args:
            coordinator: The coordinator providing data for this sensor.
        """

        super().__init__(coordinator)
        self.entity_description = BINARY_SENSOR_ACTIVE
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{BINARY_SENSOR_ACTIVE.key}"

    #
    # is_on
    #
    @property
    # BinarySensorEntity.is_on is a cached_property; we intentionally override
    # with a regular @property so it re-evaluates from coordinator data each access.
    def is_on(self) -> bool | None:  # pyright: ignore[reportIncompatibleVariableOverride]
        """Return ``True`` when the controller is actively outputting."""

        if self.coordinator.data is None:
            return None
        return self.coordinator.data.controller_active
