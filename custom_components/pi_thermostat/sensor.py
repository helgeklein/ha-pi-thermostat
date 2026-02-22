"""Sensor platform for pi_thermostat.

Provides read-only sensors exposing the PI controller's internal state:

- **output**: PI output percentage (0-100 %).
- **error**: Control error (target - current temperature).
- **p_term**: Proportional component of the output.
- **i_term**: Integral component (uses ``RestoreEntity`` for persistence across restarts).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import EntityCategory, UnitOfTemperature
from homeassistant.helpers.restore_state import RestoreEntity

from .const import (
    SENSOR_KEY_ERROR,
    SENSOR_KEY_I_TERM,
    SENSOR_KEY_OUTPUT,
    SENSOR_KEY_P_TERM,
)
from .entity import IntegrationEntity

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .coordinator import DataUpdateCoordinator
    from .data import IntegrationConfigEntry


# ---------------------------------------------------------------------------
# Sensor descriptions
# ---------------------------------------------------------------------------

SENSOR_OUTPUT = SensorEntityDescription(
    key=SENSOR_KEY_OUTPUT,
    translation_key=SENSOR_KEY_OUTPUT,
    native_unit_of_measurement="%",
    device_class=SensorDeviceClass.POWER_FACTOR,
    state_class=SensorStateClass.MEASUREMENT,
    suggested_display_precision=1,
)

SENSOR_ERROR = SensorEntityDescription(
    key=SENSOR_KEY_ERROR,
    translation_key=SENSOR_KEY_ERROR,
    native_unit_of_measurement=UnitOfTemperature.CELSIUS,
    device_class=SensorDeviceClass.TEMPERATURE,
    state_class=SensorStateClass.MEASUREMENT,
    suggested_display_precision=2,
)

SENSOR_P_TERM = SensorEntityDescription(
    key=SENSOR_KEY_P_TERM,
    translation_key=SENSOR_KEY_P_TERM,
    entity_category=EntityCategory.DIAGNOSTIC,
    state_class=SensorStateClass.MEASUREMENT,
    suggested_display_precision=2,
)

SENSOR_I_TERM = SensorEntityDescription(
    key=SENSOR_KEY_I_TERM,
    translation_key=SENSOR_KEY_I_TERM,
    entity_category=EntityCategory.DIAGNOSTIC,
    state_class=SensorStateClass.MEASUREMENT,
    suggested_display_precision=2,
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
    """Create all sensor entities for a config entry."""

    coordinator = entry.runtime_data.coordinator

    async_add_entities(
        [
            IntegrationSensor(coordinator, SENSOR_OUTPUT),
            IntegrationSensor(coordinator, SENSOR_ERROR),
            IntegrationSensor(coordinator, SENSOR_P_TERM),
            ITermSensor(coordinator),
        ]
    )


# ---------------------------------------------------------------------------
# Sensor entity classes
# ---------------------------------------------------------------------------


#
# IntegrationSensor
#
class IntegrationSensor(IntegrationEntity, SensorEntity):  # pyright: ignore[reportIncompatibleVariableOverride]
    """Generic read-only sensor backed by ``CoordinatorData``.

    The sensor's value is read from the attribute of ``CoordinatorData``
    whose name matches the entity description's *key*.
    """

    #
    # __init__
    #
    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        entity_description: SensorEntityDescription,
    ) -> None:
        """Initialize the sensor.

        Args:
            coordinator: The coordinator providing data for this sensor.
            entity_description: Descriptor defining the entity's HA properties.
        """

        super().__init__(coordinator)
        self.entity_description = entity_description
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{entity_description.key}"

    #
    # native_value
    #
    @property
    def native_value(self) -> float | None:  # pyright: ignore[reportIncompatibleVariableOverride]
        """Return the current sensor value from coordinator data."""

        if self.coordinator.data is None:
            return None
        return getattr(self.coordinator.data, self.entity_description.key, None)


# ---------------------------------------------------------------------------
# I-term sensor with RestoreEntity for integral persistence
# ---------------------------------------------------------------------------


#
# ITermSensor
#
class ITermSensor(IntegrationEntity, RestoreEntity, SensorEntity):  # pyright: ignore[reportIncompatibleVariableOverride]
    """Integral-term sensor with state persistence across restarts.

    On startup, the last known integral value is restored from HA's state
    machine and fed back into the PI controller so that the integral term
    survives HA restarts without resetting to zero.
    """

    #
    # __init__
    #
    def __init__(self, coordinator: DataUpdateCoordinator) -> None:
        """Initialize the I-term sensor.

        Args:
            coordinator: The coordinator providing data for this sensor.
        """

        super().__init__(coordinator)
        self.entity_description = SENSOR_I_TERM
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{SENSOR_I_TERM.key}"

    #
    # async_added_to_hass
    #
    async def async_added_to_hass(self) -> None:
        """Restore the integral term when the entity is added to HA.

        Steps:
        1. Call the parent implementation to register coordinator listeners.
        2. Retrieve the last stored state from HA's restore-state infrastructure.
        3. If a valid numeric state is found, pass it to the coordinator so the
           PI controller's integral term is seeded with the previous value.
        """

        await super().async_added_to_hass()

        last_state = await self.async_get_last_state()
        if last_state is None or last_state.state in (None, "", "unknown", "unavailable"):
            return

        try:
            restored_value = float(last_state.state)
        except (ValueError, TypeError):
            return

        self.coordinator.restore_integral_term(restored_value)

    #
    # native_value
    #
    @property
    def native_value(self) -> float | None:  # pyright: ignore[reportIncompatibleVariableOverride]
        """Return the current integral term from coordinator data."""

        if self.coordinator.data is None:
            return None
        return self.coordinator.data.i_term
