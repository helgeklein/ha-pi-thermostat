"""
Custom integration for PI temperature control with Home Assistant.

For more details about this integration, please refer to
https://github.com/helgeklein/ha-pi-thermostat
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.const import Platform
from homeassistant.helpers import entity_registry as er
from homeassistant.loader import async_get_loaded_integration

from .config import get_runtime_configurable_keys, resolve_entry
from .config_flow import OptionsFlowHandler
from .const import (
    DOMAIN,
    HA_OPTIONS,
    INTEGRATION_NAME,
    NUMBER_KEY_TARGET_TEMP,
    TargetTempMode,
)
from .coordinator import DataUpdateCoordinator
from .data import RuntimeData
from .log import Log

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from .data import IntegrationConfigEntry

# List of platforms provided by this integration
PLATFORMS: list[Platform] = [
    Platform.NUMBER,
    Platform.SENSOR,
    Platform.SWITCH,
]


#
# async_setup_entry
#
async def async_setup_entry(
    hass: HomeAssistant,
    entry: IntegrationConfigEntry,
) -> bool:
    """Set up the PI Thermostat integration from a config entry.

    This function is called by Home Assistant during:
    - Initial setup of the integration via the UI (after the user completes the config flow)
    - Integration reload (via UI or when config options change)
    - HA restart

    What this function does:
    - Creates the coordinator
    - Merges config + options
    - Stores runtime data on the entry
    - Starts the coordinator
    - Sets up platforms
    - Sets up the reload listener
    """

    logger = Log(entry_id=entry.entry_id)
    logger.info("Starting integration setup")

    try:
        # Create the coordinator
        coordinator = DataUpdateCoordinator(hass, entry)

        # Get configuration from options (all user settings are stored in options)
        merged_config = dict(getattr(entry, HA_OPTIONS, {}) or {})

        # Store the config in the coordinator for comparison during reload
        coordinator._merged_config = merged_config

        # Store shared state
        entry.runtime_data = RuntimeData(
            integration=async_get_loaded_integration(hass, entry.domain),
            coordinator=coordinator,
            config=merged_config,
        )

        # Call each platform's async_setup_entry()
        logger.debug(f"Setting up platforms: {PLATFORMS}")
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

        # Remove stale conditional entities from the entity registry.
        # The target_temp entity is either a number (INTERNAL mode) or a sensor
        # (EXTERNAL/CLIMATE mode), never both. Without cleanup the previously
        # created variant lingers as unavailable/greyed-out in the UI.
        _remove_stale_target_temp_entities(hass, entry)

        # Trigger initial coordinator refresh after platforms are set up
        # This ensures all entities are registered before the first state update
        logger.debug("Starting initial coordinator refresh")
        await coordinator.async_config_entry_first_refresh()

        # Register the update listener
        entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    except (OSError, ValueError, TypeError) as err:
        # "Expected" errors: only log an error message
        logger.error(f"Failed to set up {INTEGRATION_NAME} integration: {err}")
        return False
    except Exception as err:
        # "Unexpected" errors: log exception with stack trace
        logger.exception(f"Error during {INTEGRATION_NAME} setup: {err}")
        return False
    else:
        logger.info(f"{INTEGRATION_NAME} integration setup completed")
        return True


#
# _remove_stale_target_temp_entities
#
def _remove_stale_target_temp_entities(
    hass: HomeAssistant,
    entry: IntegrationConfigEntry,
) -> None:
    """Remove the target-temp entity variant that is no longer active.

    Depending on ``target_temp_mode``, the integration creates either a
    writable **number** entity (INTERNAL mode) or a read-only **sensor**
    entity (EXTERNAL / CLIMATE mode) for the target temperature.  When the
    user switches modes, the previously-created variant would linger in the
    entity registry as unavailable.  This helper removes it so the UI stays
    clean.
    """

    resolved = resolve_entry(entry)
    registry = er.async_get(hass)
    unique_id_suffix = f"_{NUMBER_KEY_TARGET_TEMP}"

    # Determine which platform's target_temp entity should NOT exist
    if resolved.target_temp_mode == TargetTempMode.INTERNAL:
        stale_platform = Platform.SENSOR
    else:
        stale_platform = Platform.NUMBER

    # Look up by unique_id and remove if present
    stale_unique_id = f"{entry.entry_id}{unique_id_suffix}"
    stale_entry = registry.async_get_entity_id(stale_platform, DOMAIN, stale_unique_id)
    if stale_entry is not None:
        registry.async_remove(stale_entry)


#
# async_get_options_flow
#
async def async_get_options_flow(entry: IntegrationConfigEntry) -> OptionsFlowHandler:
    """Return the options flow for this handler.

    This function is called by Home Assistant when:
    - The user clicks the gear icon to bring up the integration's options dialog.
    """

    return OptionsFlowHandler(entry)


#
# async_unload_entry
#
async def async_unload_entry(
    hass: HomeAssistant,
    entry: IntegrationConfigEntry,
) -> bool:
    """Handle removal of an entry."""

    logger = Log(entry_id=entry.entry_id)
    logger.info(f"Unloading {INTEGRATION_NAME} integration")

    try:
        result = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
        return result
    except (OSError, ValueError, TypeError) as err:
        # "Expected" errors: only log an error message
        logger.error(f"Error unloading {INTEGRATION_NAME} integration: {err}")
        return False
    except Exception as err:
        # "Unexpected" errors: log exception with stack trace
        logger.exception(f"Error unloading {INTEGRATION_NAME} integration: {err}")
        return False


#
# async_reload_entry
#
async def async_reload_entry(
    hass: HomeAssistant,
    entry: IntegrationConfigEntry,
) -> None:
    """Reload config entry or just refresh coordinator based on what changed.

    For runtime options that have corresponding entities (switches, numbers),
    we only need to refresh the coordinator. For structural changes, we need a full reload.
    """

    logger = Log(entry_id=entry.entry_id)

    # These keys can be changed at runtime via their corresponding entities
    # without requiring a full reload. The list is centrally defined in config.py
    # based on the runtime_configurable flag in CONF_SPECS.
    runtime_configurable_keys = get_runtime_configurable_keys()

    if hasattr(entry, "runtime_data") and entry.runtime_data:
        coordinator = entry.runtime_data.coordinator

        # Get the old configuration that the coordinator was using
        old_config = coordinator._merged_config

        # Get the new configuration from the updated entry (all settings are in options)
        new_config = dict(getattr(entry, HA_OPTIONS, {}) or {})

        # Determine which keys have actually changed
        changed_keys = {key for key in set(old_config.keys()) | set(new_config.keys()) if old_config.get(key) != new_config.get(key)}
        changes = ", ".join(f"{key}={new_config.get(key)}" for key in sorted(changed_keys))

        # If the only changes are to runtime-configurable keys, just refresh
        if changed_keys and changed_keys.issubset(runtime_configurable_keys):
            logger.info(f"Runtime settings change detected ({changes}), refreshing coordinator")

            # Update the stored config with new values
            coordinator._merged_config = new_config
            entry.runtime_data.config = new_config

            # Trigger a coordinator refresh to apply the changes
            await coordinator.async_request_refresh()
            return

    # For all other changes (structural, new keys, etc.), do a full reload
    logger.info(f"Reloading {INTEGRATION_NAME} integration")
    await hass.config_entries.async_reload(entry.entry_id)


# Re-export common package-level symbols for convenience imports in tooling/tests
__all__ = [
    "DOMAIN",
    "PLATFORMS",
    "async_setup_entry",
    "async_unload_entry",
    "async_reload_entry",
]
