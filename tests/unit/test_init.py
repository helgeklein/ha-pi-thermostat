"""Tests for __init__.py.

Tests cover:
- async_setup_entry: happy path (via test_entities.py), expected errors, unexpected errors.
- async_get_options_flow: returns OptionsFlowHandler instance.
- async_unload_entry: happy path (via test_entities.py), expected errors, unexpected errors.
- async_reload_entry: runtime-only changes (coordinator refresh), structural changes
  (full reload), no runtime_data (full reload), mixed changes (full reload),
  no changes (no-op).
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

from homeassistant.core import HomeAssistant

from custom_components.pi_thermostat import (
    async_get_options_flow,
    async_reload_entry,
    async_unload_entry,
)
from custom_components.pi_thermostat.config_flow import OptionsFlowHandler
from custom_components.pi_thermostat.const import DOMAIN, OperatingMode, TargetTempMode

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_entry(options: dict[str, Any] | None = None) -> Any:
    """Create a MockConfigEntry."""

    from pytest_homeassistant_custom_component.common import MockConfigEntry

    return MockConfigEntry(
        domain=DOMAIN,
        title="PI Thermostat",
        data={},
        options=options or _default_options(),
    )


def _default_options(**overrides: Any) -> dict[str, Any]:
    """Return a minimal valid options dict."""

    base: dict[str, Any] = {
        "enabled": True,
        "operating_mode": OperatingMode.HEAT,
        "temp_sensor": "sensor.temperature",
        "target_temp_mode": "internal",
        "target_temp": 20.0,
    }
    base.update(overrides)
    return base


async def _setup_integration(
    hass: HomeAssistant,
    options: dict[str, Any] | None = None,
) -> Any:
    """Set up the integration with given options and return the entry."""

    entry = _make_entry(options)
    entry.add_to_hass(hass)

    with patch(
        "custom_components.pi_thermostat.ha_interface.HomeAssistantInterface.get_temperature",
        return_value=20.0,
    ):
        result = await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert result is True
    return entry


# ===========================================================================
# async_setup_entry error handling
# ===========================================================================


class TestSetupEntryErrors:
    """Test async_setup_entry exception handling."""

    async def test_expected_error_returns_false(self, hass: HomeAssistant) -> None:
        """OSError/ValueError/TypeError during setup returns False."""

        entry = _make_entry()
        entry.add_to_hass(hass)

        with patch(
            "custom_components.pi_thermostat.coordinator.DataUpdateCoordinator.__init__",
            side_effect=ValueError("bad sensor config"),
        ):
            result = await hass.config_entries.async_setup(entry.entry_id)
            await hass.async_block_till_done()

        assert result is False

    async def test_unexpected_error_returns_false(self, hass: HomeAssistant) -> None:
        """Unexpected Exception during setup returns False."""

        entry = _make_entry()
        entry.add_to_hass(hass)

        with patch(
            "custom_components.pi_thermostat.coordinator.DataUpdateCoordinator.__init__",
            side_effect=RuntimeError("unexpected failure"),
        ):
            result = await hass.config_entries.async_setup(entry.entry_id)
            await hass.async_block_till_done()

        assert result is False


# ===========================================================================
# async_get_options_flow
# ===========================================================================


class TestGetOptionsFlow:
    """Test async_get_options_flow."""

    async def test_returns_options_flow_handler(self) -> None:
        """Returns an OptionsFlowHandler instance."""

        entry = _make_entry()
        handler = await async_get_options_flow(entry)
        assert isinstance(handler, OptionsFlowHandler)


# ===========================================================================
# async_unload_entry error handling
# ===========================================================================


class TestUnloadEntryErrors:
    """Test async_unload_entry exception handling."""

    async def test_expected_error_returns_false(self, hass: HomeAssistant) -> None:
        """OSError during unload returns False."""

        entry = await _setup_integration(hass)

        with patch.object(
            hass.config_entries,
            "async_unload_platforms",
            side_effect=OSError("platform unload failed"),
        ):
            result = await async_unload_entry(hass, entry)

        assert result is False

    async def test_unexpected_error_returns_false(self, hass: HomeAssistant) -> None:
        """Unexpected Exception during unload returns False."""

        entry = await _setup_integration(hass)

        with patch.object(
            hass.config_entries,
            "async_unload_platforms",
            side_effect=RuntimeError("unexpected unload error"),
        ):
            result = await async_unload_entry(hass, entry)

        assert result is False


# ===========================================================================
# async_reload_entry — smart reload logic
# ===========================================================================


class TestReloadEntry:
    """Test async_reload_entry smart reload logic."""

    async def test_runtime_only_change_refreshes_coordinator(
        self,
        hass: HomeAssistant,
    ) -> None:
        """When only runtime-configurable keys change, coordinator refreshes (no full reload)."""

        entry = await _setup_integration(hass)
        coordinator = entry.runtime_data.coordinator

        # Patch BEFORE updating options, because async_update_entry fires
        # the update listener (async_reload_entry) synchronously.
        with (
            patch.object(
                coordinator,
                "async_request_refresh",
                new_callable=AsyncMock,
            ) as mock_refresh,
            patch.object(
                hass.config_entries,
                "async_reload",
                new_callable=AsyncMock,
            ) as mock_reload,
        ):
            hass.config_entries.async_update_entry(
                entry,
                options={**entry.options, "target_temp": 25.0},
            )
            await hass.async_block_till_done()

        # Coordinator was refreshed, not fully reloaded
        mock_refresh.assert_awaited_once()
        mock_reload.assert_not_awaited()

        # Config was updated in coordinator and runtime_data
        assert coordinator._merged_config["target_temp"] == 25.0
        assert entry.runtime_data.config["target_temp"] == 25.0

    async def test_structural_change_triggers_full_reload(
        self,
        hass: HomeAssistant,
    ) -> None:
        """When structural keys change, a full reload is triggered."""

        entry = await _setup_integration(hass)

        with patch.object(
            hass.config_entries,
            "async_reload",
            new_callable=AsyncMock,
        ) as mock_reload:
            hass.config_entries.async_update_entry(
                entry,
                options={**entry.options, "temp_sensor": "sensor.new_temperature"},
            )
            await hass.async_block_till_done()

        mock_reload.assert_awaited_once_with(entry.entry_id)

    async def test_mixed_change_triggers_full_reload(
        self,
        hass: HomeAssistant,
    ) -> None:
        """When both runtime and structural keys change, a full reload is triggered."""

        entry = await _setup_integration(hass)

        with patch.object(
            hass.config_entries,
            "async_reload",
            new_callable=AsyncMock,
        ) as mock_reload:
            hass.config_entries.async_update_entry(
                entry,
                options={
                    **entry.options,
                    "target_temp": 30.0,
                    "temp_sensor": "sensor.other",
                },
            )
            await hass.async_block_till_done()

        mock_reload.assert_awaited_once_with(entry.entry_id)

    async def test_no_runtime_data_triggers_full_reload(
        self,
        hass: HomeAssistant,
    ) -> None:
        """When runtime_data is unavailable, falls through to full reload."""

        entry = _make_entry()
        entry.add_to_hass(hass)

        # Entry has no runtime_data (integration hasn't completed setup)
        with patch.object(
            hass.config_entries,
            "async_reload",
            new_callable=AsyncMock,
        ) as mock_reload:
            await async_reload_entry(hass, entry)

        mock_reload.assert_awaited_once_with(entry.entry_id)

    async def test_no_changes_triggers_full_reload(
        self,
        hass: HomeAssistant,
    ) -> None:
        """When options haven't actually changed, falls through to full reload."""

        entry = await _setup_integration(hass)

        # Don't change any options — changed_keys will be empty
        with (
            patch.object(
                entry.runtime_data.coordinator,
                "async_request_refresh",
                new_callable=AsyncMock,
            ) as mock_refresh,
            patch.object(
                hass.config_entries,
                "async_reload",
                new_callable=AsyncMock,
            ) as mock_reload,
        ):
            await async_reload_entry(hass, entry)

        # Empty changed_keys → not a subset → falls through to full reload
        mock_refresh.assert_not_awaited()
        mock_reload.assert_awaited_once_with(entry.entry_id)

    async def test_multiple_runtime_changes(
        self,
        hass: HomeAssistant,
    ) -> None:
        """Multiple runtime-only key changes still just refresh coordinator."""

        entry = await _setup_integration(hass)
        coordinator = entry.runtime_data.coordinator

        with (
            patch.object(
                coordinator,
                "async_request_refresh",
                new_callable=AsyncMock,
            ) as mock_refresh,
            patch.object(
                hass.config_entries,
                "async_reload",
                new_callable=AsyncMock,
            ) as mock_reload,
        ):
            hass.config_entries.async_update_entry(
                entry,
                options={
                    **entry.options,
                    "target_temp": 22.0,
                    "proportional_band": 8.0,
                    "output_min": 5.0,
                },
            )
            await hass.async_block_till_done()

        mock_refresh.assert_awaited_once()
        mock_reload.assert_not_awaited()


# ===========================================================================
# Stale target_temp entity cleanup
# ===========================================================================


class TestStaleEntityCleanup:
    """Test that switching target_temp_mode removes the stale entity variant."""

    async def test_internal_mode_removes_stale_sensor(
        self,
        hass: HomeAssistant,
    ) -> None:
        """In INTERNAL mode, a leftover target_temp sensor entity is removed."""

        from homeassistant.const import Platform
        from homeassistant.helpers import entity_registry as er

        # First, set up in CLIMATE mode so a target_temp sensor is created
        entry = await _setup_integration(
            hass,
            _default_options(
                target_temp_mode=TargetTempMode.CLIMATE,
                climate_entity="climate.living_room",
            ),
        )

        registry = er.async_get(hass)
        sensor_uid = f"{entry.entry_id}_target_temp"

        # Verify the sensor entity exists
        sensor_entity_id = registry.async_get_entity_id(Platform.SENSOR, DOMAIN, sensor_uid)
        assert sensor_entity_id is not None, "sensor should exist in CLIMATE mode"

        # Verify no number entity
        number_entity_id = registry.async_get_entity_id(Platform.NUMBER, DOMAIN, sensor_uid)
        assert number_entity_id is None, "number should not exist in CLIMATE mode"

        # Now reload in INTERNAL mode
        with (
            patch.object(
                hass.config_entries,
                "async_reload",
                wraps=hass.config_entries.async_reload,
            ),
            patch(
                "custom_components.pi_thermostat.ha_interface.HomeAssistantInterface.get_temperature",
                return_value=20.0,
            ),
        ):
            hass.config_entries.async_update_entry(
                entry,
                options={**entry.options, "target_temp_mode": TargetTempMode.INTERNAL, "target_temp": 20.0},
            )
            await hass.async_block_till_done()

        # The stale sensor entity should have been removed
        sensor_entity_id = registry.async_get_entity_id(Platform.SENSOR, DOMAIN, sensor_uid)
        assert sensor_entity_id is None, "stale sensor should be removed after switching to INTERNAL"

    async def test_climate_mode_removes_stale_number(
        self,
        hass: HomeAssistant,
    ) -> None:
        """In CLIMATE mode, a leftover target_temp number entity is removed."""

        from homeassistant.const import Platform
        from homeassistant.helpers import entity_registry as er

        # First, set up in INTERNAL mode so a target_temp number is created
        entry = await _setup_integration(hass, _default_options())

        registry = er.async_get(hass)
        number_uid = f"{entry.entry_id}_target_temp"

        # Verify the number entity exists
        number_entity_id = registry.async_get_entity_id(Platform.NUMBER, DOMAIN, number_uid)
        assert number_entity_id is not None, "number should exist in INTERNAL mode"

        # Now reload in CLIMATE mode
        with (
            patch.object(
                hass.config_entries,
                "async_reload",
                wraps=hass.config_entries.async_reload,
            ),
            patch(
                "custom_components.pi_thermostat.ha_interface.HomeAssistantInterface.get_temperature",
                return_value=20.0,
            ),
        ):
            hass.config_entries.async_update_entry(
                entry,
                options={
                    **entry.options,
                    "target_temp_mode": TargetTempMode.CLIMATE,
                    "climate_entity": "climate.living_room",
                },
            )
            await hass.async_block_till_done()

        # The stale number entity should have been removed
        number_entity_id = registry.async_get_entity_id(Platform.NUMBER, DOMAIN, number_uid)
        assert number_entity_id is None, "stale number should be removed after switching to CLIMATE"
