"""Number platform for pi_thermostat.

Provides writable number entities for runtime-configurable PI controller
parameters.  When a user adjusts a value, ``_async_persist_option()`` writes
it to the config entry's options, which triggers the smart-reload listener
in ``__init__.py`` (coordinator refresh for runtime-configurable keys,
full reload otherwise).

Entities:

- **proportional_band** — Temperature range in K over which output spans 0–100 %.
- **integral_time** — Reset time in minutes for the integral action.
- **target_temp** — Internal setpoint (only effective when target_temp_mode = internal).
- **output_min / output_max** — Output clamping limits (%).
- **update_interval** — Coordinator update interval (seconds).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.const import EntityCategory, UnitOfTemperature, UnitOfTime

from .config import ConfKeys, resolve_entry
from .const import (
    NUMBER_KEY_INT_TIME,
    NUMBER_KEY_OUTPUT_MAX,
    NUMBER_KEY_OUTPUT_MIN,
    NUMBER_KEY_PROP_BAND,
    NUMBER_KEY_TARGET_TEMP,
    NUMBER_KEY_UPDATE_INTERVAL,
)
from .entity import IntegrationEntity

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .coordinator import DataUpdateCoordinator
    from .data import IntegrationConfigEntry


# ---------------------------------------------------------------------------
# Number descriptions
# ---------------------------------------------------------------------------

NUMBER_PROP_BAND = NumberEntityDescription(
    key=NUMBER_KEY_PROP_BAND,
    translation_key=NUMBER_KEY_PROP_BAND,
    entity_category=EntityCategory.CONFIG,
    icon="mdi:sine-wave",
    native_min_value=0.5,
    native_max_value=30.0,
    native_step=0.1,
    mode=NumberMode.BOX,
    native_unit_of_measurement="K",
)

NUMBER_INT_TIME = NumberEntityDescription(
    key=NUMBER_KEY_INT_TIME,
    translation_key=NUMBER_KEY_INT_TIME,
    entity_category=EntityCategory.CONFIG,
    icon="mdi:timer-outline",
    native_min_value=1.0,
    native_max_value=600.0,
    native_step=1.0,
    mode=NumberMode.BOX,
    native_unit_of_measurement=UnitOfTime.MINUTES,
)

NUMBER_TARGET_TEMP = NumberEntityDescription(
    key=NUMBER_KEY_TARGET_TEMP,
    translation_key=NUMBER_KEY_TARGET_TEMP,
    entity_category=None,  # Primary control. Appears in the "Controls" section of the UI, not in "Configuration".
    device_class=NumberDeviceClass.TEMPERATURE,
    native_min_value=5.0,
    native_max_value=35.0,
    native_step=0.1,
    mode=NumberMode.BOX,
    native_unit_of_measurement=UnitOfTemperature.CELSIUS,
)

NUMBER_OUTPUT_MIN = NumberEntityDescription(
    key=NUMBER_KEY_OUTPUT_MIN,
    translation_key=NUMBER_KEY_OUTPUT_MIN,
    entity_category=EntityCategory.CONFIG,
    icon="mdi:arrow-collapse-down",
    native_min_value=0.0,
    native_max_value=100.0,
    native_step=1.0,
    mode=NumberMode.BOX,
    native_unit_of_measurement="%",
)

NUMBER_OUTPUT_MAX = NumberEntityDescription(
    key=NUMBER_KEY_OUTPUT_MAX,
    translation_key=NUMBER_KEY_OUTPUT_MAX,
    entity_category=EntityCategory.CONFIG,
    icon="mdi:arrow-collapse-up",
    native_min_value=0.0,
    native_max_value=100.0,
    native_step=1.0,
    mode=NumberMode.BOX,
    native_unit_of_measurement="%",
)

NUMBER_UPDATE_INTERVAL = NumberEntityDescription(
    key=NUMBER_KEY_UPDATE_INTERVAL,
    translation_key=NUMBER_KEY_UPDATE_INTERVAL,
    entity_category=EntityCategory.CONFIG,
    icon="mdi:update",
    native_min_value=10.0,
    native_max_value=600.0,
    native_step=10.0,
    mode=NumberMode.BOX,
    native_unit_of_measurement=UnitOfTime.SECONDS,
)

# Map each description to the ConfKeys enum member it controls
_NUMBERS: list[tuple[NumberEntityDescription, ConfKeys]] = [
    (NUMBER_PROP_BAND, ConfKeys.PROPORTIONAL_BAND),
    (NUMBER_INT_TIME, ConfKeys.INTEGRAL_TIME),
    (NUMBER_TARGET_TEMP, ConfKeys.TARGET_TEMP),
    (NUMBER_OUTPUT_MIN, ConfKeys.OUTPUT_MIN),
    (NUMBER_OUTPUT_MAX, ConfKeys.OUTPUT_MAX),
    (NUMBER_UPDATE_INTERVAL, ConfKeys.UPDATE_INTERVAL),
]


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
    """Create all number entities for a config entry."""

    coordinator = entry.runtime_data.coordinator

    async_add_entities([IntegrationNumber(coordinator, desc, conf_key) for desc, conf_key in _NUMBERS])


# ---------------------------------------------------------------------------
# Number entity class
# ---------------------------------------------------------------------------


#
# IntegrationNumber
#
class IntegrationNumber(IntegrationEntity, NumberEntity):  # pyright: ignore[reportIncompatibleVariableOverride]
    """Writable number entity backed by a config-entry option.

    Reading: resolves the current value from the config entry via ``resolve_entry()``.
    Writing: persists the new value to the config entry's options, which triggers
    the smart-reload listener in ``__init__.py``.
    """

    #
    # __init__
    #
    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        entity_description: NumberEntityDescription,
        config_key: ConfKeys,
    ) -> None:
        """Initialize the number entity.

        Args:
            coordinator: The coordinator managing this integration instance.
            entity_description: Descriptor defining the entity's HA properties.
            config_key: The ``ConfKeys`` member this entity reads/writes.
        """

        super().__init__(coordinator)
        self.entity_description = entity_description
        self._config_key = config_key
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{entity_description.key}"

    #
    # native_value
    #
    @property
    def native_value(self) -> float:  # pyright: ignore[reportIncompatibleVariableOverride]
        """Return the current value from the resolved config."""

        resolved = resolve_entry(self.coordinator.config_entry)
        return float(resolved.get(self._config_key))

    #
    # async_set_native_value
    #
    async def async_set_native_value(self, value: float) -> None:
        """Persist the new value to the config entry options.

        Args:
            value: The new value set by the user.
        """

        await self._async_persist_option(self._config_key.value, value)

    #
    # _async_persist_option
    #
    async def _async_persist_option(self, config_key: str, value: float) -> None:
        """Write a single option to the config entry.

        The update triggers the options-update listener registered in
        ``__init__.py``, which decides between a coordinator refresh
        (for runtime-configurable keys) and a full reload.

        Args:
            config_key: The configuration key string to update.
            value: The new value for the key.
        """

        entry = self.coordinator.config_entry
        current_options = dict(entry.options or {})
        current_options[config_key] = value
        self.coordinator.hass.config_entries.async_update_entry(entry, options=current_options)
