"""Switch platform for pi_thermostat.

Provides a single writable switch:

- **enabled** — Master on/off. When off, the PI controller is paused and
  output is 0 %.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.const import EntityCategory

from .config import ConfKeys, resolve_entry
from .const import SWITCH_KEY_ENABLED
from .entity import IntegrationEntity

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .coordinator import DataUpdateCoordinator
    from .data import IntegrationConfigEntry


# ---------------------------------------------------------------------------
# Switch descriptions
# ---------------------------------------------------------------------------

SWITCH_ENABLED = SwitchEntityDescription(
    key=SWITCH_KEY_ENABLED,
    translation_key=SWITCH_KEY_ENABLED,
    entity_category=EntityCategory.CONFIG,
    icon="mdi:toggle-switch-outline",
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
    """Create all switch entities for a config entry."""

    coordinator = entry.runtime_data.coordinator

    async_add_entities(
        [
            IntegrationSwitch(coordinator, SWITCH_ENABLED, ConfKeys.ENABLED),
        ]
    )


# ---------------------------------------------------------------------------
# Switch entity class
# ---------------------------------------------------------------------------


#
# IntegrationSwitch
#
class IntegrationSwitch(IntegrationEntity, SwitchEntity):  # pyright: ignore[reportIncompatibleVariableOverride]
    """Boolean switch backed by a config-entry option.

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
        entity_description: SwitchEntityDescription,
        config_key: ConfKeys,
    ) -> None:
        """Initialize the switch entity.

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
    # is_on
    #
    @property
    def is_on(self) -> bool:  # pyright: ignore[reportIncompatibleVariableOverride]
        """Return whether the switch is currently on."""

        resolved = resolve_entry(self.coordinator.config_entry)
        return bool(resolved.get(self._config_key))

    #
    # async_turn_on
    #
    async def async_turn_on(self, **_: Any) -> None:
        """Turn the switch on."""

        await self._async_persist_option(self._config_key.value, True)

    #
    # async_turn_off
    #
    async def async_turn_off(self, **_: Any) -> None:
        """Turn the switch off."""

        await self._async_persist_option(self._config_key.value, False)

    #
    # _async_persist_option
    #
    async def _async_persist_option(self, config_key: str, value: bool) -> None:
        """Write a single boolean option to the config entry.

        The update triggers the options-update listener registered in
        ``__init__.py``, which decides between a coordinator refresh
        (for runtime-configurable keys) and a full reload.

        Args:
            config_key: The configuration key string to update.
            value: The new boolean value.
        """

        entry = self.coordinator.config_entry
        current_options = dict(entry.options or {})
        current_options[config_key] = value
        self.coordinator.hass.config_entries.async_update_entry(entry, options=current_options)
