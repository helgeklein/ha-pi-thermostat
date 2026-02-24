"""PI thermostat coordinator — update loop.

Reads temperatures, delegates to the PI controller, and returns
``CoordinatorData`` consumed by all entities.

The ``_async_update_data`` cycle runs on every update interval:

 1. Resolve configuration from config entry options.
 1b. Check the enabled flag — return paused result if off (preserves last state).
 2. Auto-disable when the climate entity's HVAC mode is "off".
 3. Determine heating / cooling direction (fixed or from climate entity).
 4. Read the current temperature (sensor or climate entity).
 5. Determine the target temperature (internal, external, or climate).
 6. Handle sensor faults (shutdown immediately or hold then shutdown).
 7. Apply any runtime tuning changes to the PI controller.
 8. Run the PI controller to get output, deviation, P-term, and I-term.
 9. Write the output value to the configured output entity (optional).
10. Return ``CoordinatorData`` for consumption by all entities.
"""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING, Any

from homeassistant.components.climate.const import HVACAction, HVACMode
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator as BaseCoordinator,
)
from homeassistant.helpers.update_coordinator import (
    UpdateFailed,
)

from .config import ResolvedConfig, resolve_entry
from .const import (
    DOMAIN,
    HA_OPTIONS,
    SENSOR_FAULT_GRACE_PERIOD_SECONDS,
    OperatingMode,
    SensorFaultMode,
)
from .data import CoordinatorData
from .ha_interface import HomeAssistantInterface
from .log import Log
from .pi_controller import PIController

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from .data import IntegrationConfigEntry


# ---------------------------------------------------------------------------
# DataUpdateCoordinator
# ---------------------------------------------------------------------------


#
# DataUpdateCoordinator
#
class DataUpdateCoordinator(BaseCoordinator[CoordinatorData]):
    """PI thermostat update coordinator."""

    config_entry: IntegrationConfigEntry

    #
    # __init__
    #
    def __init__(self, hass: HomeAssistant, config_entry: IntegrationConfigEntry) -> None:
        """Initialize the coordinator.

        Args:
            hass: Home Assistant instance.
            config_entry: The integration's config entry.
        """

        # Instance-specific logger
        self._logger = Log(entry_id=config_entry.entry_id)

        resolved = resolve_entry(config_entry)

        super().__init__(
            hass,
            self._logger.underlying_logger,
            name=DOMAIN,
            update_interval=timedelta(seconds=resolved.update_interval),
            config_entry=config_entry,
        )
        self.config_entry = config_entry

        # Merged config dict for reload-comparison in __init__.py
        self._merged_config: dict[str, Any] = {}

        # HA abstraction layer
        self._ha = HomeAssistantInterface(hass, self._logger)

        # PI controller — created with initial resolved settings
        self._pi = PIController(
            proportional_band=resolved.proportional_band,
            integral_time_min=resolved.integral_time,
            output_min=resolved.output_min,
            output_max=resolved.output_max,
            sample_time=float(resolved.update_interval),
            setpoint=resolved.target_temp,
            is_cooling=(resolved.operating_mode == OperatingMode.COOL),
        )

        # Sensor-fault tracking for HOLD mode
        self._fault_cycles: int = 0
        self._last_good_output: float | None = None

        # Last coordinator result — used to preserve state when paused
        self._last_data: CoordinatorData | None = None

        # Track last-applied tunings to detect changes
        self._last_prop_band: float = resolved.proportional_band
        self._last_int_time: float = resolved.integral_time
        self._last_output_min: float = resolved.output_min
        self._last_output_max: float = resolved.output_max
        self._last_update_interval: int = resolved.update_interval

        self._logger.info(
            "Coordinator initialized: update_interval=%s s, prop_band=%s K, int_time=%s min, mode=%s",
            resolved.update_interval,
            resolved.proportional_band,
            resolved.integral_time,
            resolved.operating_mode,
        )

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    #
    # restore_integral_term
    #
    def restore_integral_term(self, value: float) -> None:
        """Restore the integral term after a restart (called by the i_term sensor).

        Args:
            value: Previously persisted integral term.
        """

        self._pi.restore_integral_term(value)
        self._logger.info("Restored integral term: %s", value)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    #
    # _resolve
    #
    def _resolve(self) -> ResolvedConfig:
        """Return resolved settings from the config entry options."""

        from .config import resolve

        opts = dict(getattr(self.config_entry, HA_OPTIONS, {}) or {})
        return resolve(opts)

    #
    # _paused_result
    #
    def _paused_result(self) -> CoordinatorData:
        """Return a CoordinatorData that preserves the last state (controller paused).

        When no previous data exists (e.g. first cycle after startup with
        the enabled switch off), returns a safe default with output = 0.
        The output entity is **not** written to, so whatever value the
        external entity already has is preserved.
        """

        if self._last_data is not None:
            return CoordinatorData(
                output=self._last_data.output,
                deviation=self._last_data.deviation,
                p_term=self._last_data.p_term,
                i_term=self._last_data.i_term,
                current_temp=self._last_data.current_temp,
                target_temp=self._last_data.target_temp,
                sensor_available=self._last_data.sensor_available,
            )

        return self._unknown_result()

    #
    # _shutdown_result
    #
    @staticmethod
    def _shutdown_result(
        *,
        current_temp: float | None = None,
        target_temp: float | None = None,
        sensor_available: bool = True,
    ) -> CoordinatorData:
        """Return a CoordinatorData with output = 0 (shutdown / auto-disabled)."""

        return CoordinatorData(
            output=0.0,
            deviation=None,
            p_term=None,
            i_term=None,
            current_temp=current_temp,
            target_temp=target_temp,
            sensor_available=sensor_available,
        )

    #
    # _unknown_result
    #
    @staticmethod
    def _unknown_result(
        *,
        current_temp: float | None = None,
        target_temp: float | None = None,
        sensor_available: bool = True,
    ) -> CoordinatorData:
        """Return a CoordinatorData with output = None (no known-good value yet).

        Used when the coordinator cannot determine a valid output and should
        not change whatever value entities already have (e.g. their restored
        state after a restart).
        """

        return CoordinatorData(
            output=None,
            deviation=None,
            p_term=None,
            i_term=None,
            current_temp=current_temp,
            target_temp=target_temp,
            sensor_available=sensor_available,
        )

    #
    # _async_write_output
    #
    async def _async_write_output(self, resolved: ResolvedConfig, output: float) -> None:
        """Write the output value to the configured output entity.

        Logs a warning on failure but never raises.

        Args:
            resolved: Current resolved configuration.
            output: Output value to write.
        """

        if not resolved.output_entity:
            return

        try:
            await self._ha.set_output(resolved.output_entity, output)
        except Exception:  # noqa: BLE001
            self._logger.warning(
                "Failed to write output %s to %s",
                output,
                resolved.output_entity,
            )

    #
    # _read_current_temp
    #
    def _read_current_temp(self, resolved: ResolvedConfig) -> float | None:
        """Read the current temperature from the configured source.

        Priority:
        1. Dedicated temperature sensor entity (temp_sensor).
        2. Climate entity's current_temperature attribute.

        Returns:
            Temperature as float, or ``None`` if unavailable.
        """

        if resolved.temp_sensor:
            return self._ha.get_temperature(resolved.temp_sensor)

        if resolved.climate_entity:
            return self._ha.get_climate_current_temperature(resolved.climate_entity)

        return None

    #
    # _read_target_temp
    #
    def _read_target_temp(self, resolved: ResolvedConfig) -> float | None:
        """Read the target temperature from the configured source.

        Returns:
            Target temperature, or ``None`` if unavailable from an external source.
        """

        from .const import TargetTempMode

        mode = resolved.target_temp_mode

        if mode == TargetTempMode.INTERNAL:
            return resolved.target_temp

        if mode == TargetTempMode.EXTERNAL and resolved.target_temp_entity:
            return self._ha.get_target_temperature(resolved.target_temp_entity)

        if mode == TargetTempMode.CLIMATE and resolved.climate_entity:
            return self._ha.get_climate_target_temperature(resolved.climate_entity)

        # Fallback — no valid source
        return None

    #
    # _apply_tuning_changes
    #
    def _apply_tuning_changes(self, resolved: ResolvedConfig) -> None:
        """Detect and apply any runtime tuning changes to the PI controller."""

        # Proportional band or integral time changed
        if resolved.proportional_band != self._last_prop_band or resolved.integral_time != self._last_int_time:
            self._pi.update_tunings(resolved.proportional_band, resolved.integral_time)
            self._last_prop_band = resolved.proportional_band
            self._last_int_time = resolved.integral_time
            self._logger.info(
                "Tunings updated: prop_band=%s K, int_time=%s min",
                resolved.proportional_band,
                resolved.integral_time,
            )

        # Output limits changed
        if resolved.output_min != self._last_output_min or resolved.output_max != self._last_output_max:
            self._pi.update_output_limits(resolved.output_min, resolved.output_max)
            self._last_output_min = resolved.output_min
            self._last_output_max = resolved.output_max
            self._logger.info(
                "Output limits updated: min=%s, max=%s",
                resolved.output_min,
                resolved.output_max,
            )

        # Update interval changed
        if resolved.update_interval != self._last_update_interval:
            new_interval = resolved.update_interval
            self._pi.update_sample_time(float(new_interval))
            self.update_interval = timedelta(seconds=new_interval)
            self._last_update_interval = new_interval
            self._logger.info("Update interval changed to %s s", new_interval)

    #
    # _determine_cooling
    #
    def _determine_cooling(self, resolved: ResolvedConfig) -> bool:
        """Determine whether the controller should operate in cooling mode.

        Returns:
            ``True`` if cooling, ``False`` if heating.
        """

        mode = resolved.operating_mode

        if mode == OperatingMode.COOL:
            return True
        if mode == OperatingMode.HEAT:
            return False

        # heat_cool → read from climate entity
        if resolved.climate_entity:
            action = self._ha.get_climate_hvac_action(resolved.climate_entity)
            if action == HVACAction.COOLING:
                return True

        # Default to heating when action is unknown / idle
        return False

    # ------------------------------------------------------------------
    # Core update loop
    # ------------------------------------------------------------------

    #
    # _async_update_data
    #
    async def _async_update_data(self) -> CoordinatorData:
        """Run one PI control cycle.

        This is called by HA's DataUpdateCoordinator on every update interval,
        on first refresh, and on manual refresh requests.

        Returns:
            ``CoordinatorData`` consumed by all entities.

        Raises:
            UpdateFailed: On critical configuration errors.
        """

        # ── Step 1: Resolve config ──────────────────────────────────────
        try:
            resolved = self._resolve()
        except Exception as err:
            self._logger.error("Configuration error: %s", err)
            raise UpdateFailed(f"Configuration error: {err}") from err

        # ── Step 1b: Check enabled flag (pause — preserve last state) ──
        if not resolved.enabled:
            self._logger.debug("Controller paused via enabled flag")
            return self._paused_result()

        # ── Step 2: Auto-disable on HVAC off ────────────────────────────
        if resolved.climate_entity and resolved.auto_disable_on_hvac_off:
            hvac_mode = self._ha.get_climate_hvac_mode(resolved.climate_entity)
            if hvac_mode == HVACMode.OFF:
                self._logger.debug("Auto-disabled: climate entity hvac_mode is off")
                await self._async_write_output(resolved, 0.0)
                return self._shutdown_result()

        # ── Step 3: Determine heating / cooling direction ───────────────
        is_cooling = self._determine_cooling(resolved)
        self._pi.set_cooling(is_cooling)

        # ── Step 4: Read current temperature ────────────────────────────
        current_temp = self._read_current_temp(resolved)

        # ── Step 5: Determine target temperature ────────────────────────
        target_temp = self._read_target_temp(resolved)

        if target_temp is not None:
            self._pi.set_target(target_temp)

        # ── Step 6: Handle sensor faults ────────────────────────────────
        if current_temp is None:
            return await self._async_handle_sensor_fault(resolved, target_temp)

        # Sensor is OK — reset fault counter
        self._fault_cycles = 0

        # ── Step 7: Apply tuning changes ────────────────────────────────
        self._apply_tuning_changes(resolved)

        # ── Step 8: Run PI controller ───────────────────────────────────
        result = self._pi.update(current_temp)

        # Track last good output for HOLD fault mode
        self._last_good_output = result.output

        # ── Step 9: Write output to entity (optional) ───────────────────
        await self._async_write_output(resolved, result.output)

        # ── Step 10: Return CoordinatorData ─────────────────────────────
        data = CoordinatorData(
            output=result.output,
            deviation=result.deviation,
            p_term=result.p_term,
            i_term=result.i_term,
            current_temp=current_temp,
            target_temp=target_temp,
            sensor_available=True,
        )
        self._last_data = data
        return data

    #
    # _async_handle_sensor_fault
    #
    async def _async_handle_sensor_fault(
        self,
        resolved: ResolvedConfig,
        target_temp: float | None,
    ) -> CoordinatorData:
        """Handle a sensor fault (current temperature unavailable).

        Args:
            resolved: Current resolved configuration.
            target_temp: Current target temperature (may be ``None``).

        Returns:
            ``CoordinatorData`` with either held output or shutdown (output=0).
        """

        fault_mode = resolved.sensor_fault_mode

        if fault_mode == SensorFaultMode.HOLD and self._last_good_output is not None:
            grace_cycles = max(
                1,
                SENSOR_FAULT_GRACE_PERIOD_SECONDS // max(resolved.update_interval, 1),
            )

            self._fault_cycles += 1

            if self._fault_cycles <= grace_cycles:
                self._logger.warning(
                    "Sensor unavailable (cycle %s/%s) — holding last output %s",
                    self._fault_cycles,
                    grace_cycles,
                    self._last_good_output,
                )
                return CoordinatorData(
                    output=self._last_good_output,
                    deviation=None,
                    p_term=None,
                    i_term=None,
                    current_temp=None,
                    target_temp=target_temp,
                    sensor_available=False,
                )

            # Grace period exceeded — fall through to shutdown
            self._logger.warning("Sensor unavailable — grace period exceeded, shutting down output")

        elif fault_mode == SensorFaultMode.HOLD:
            # HOLD mode but no prior good output (e.g. first cycle after restart).
            # Return unknown result so entity states are not changed from their
            # restored values — avoids sending a spurious 0 % on restart.
            self._logger.warning("Sensor unavailable — no prior output available, waiting for sensor")
            return self._unknown_result(
                target_temp=target_temp,
                sensor_available=False,
            )

        else:
            self._logger.warning("Sensor unavailable — shutting down output (shutdown mode)")

        await self._async_write_output(resolved, 0.0)
        return self._shutdown_result(
            target_temp=target_temp,
            sensor_available=False,
        )
