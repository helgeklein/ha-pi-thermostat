"""PI controller for HVAC temperature control.

Pure Python module with no Home Assistant imports. Wraps the simple-pid library
to provide a PI (proportional-integral) controller using HVAC-standard
parameterization (proportional band, integral time).

The simple-pid library handles:
- Anti-windup via output limits (integral term is clamped automatically).
- Sample time enforcement (no new output if called too frequently).
"""

from __future__ import annotations

from dataclasses import dataclass

from simple_pid import PID

# ---------------------------------------------------------------------------
# PIResult
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PIResult:
    """Result of a single PI computation.

    Attributes:
        output: Controller output percentage (clamped to output limits).
        deviation: Setpoint minus current temperature (positive = needs heating).
        p_term: Proportional component of the output.
        i_term: Integral component of the output.
    """

    output: float
    deviation: float
    p_term: float
    i_term: float


# ---------------------------------------------------------------------------
# PIController
# ---------------------------------------------------------------------------


#
# PIController
#
class PIController:
    """PI controller wrapping simple-pid for HVAC temperature control.

    Uses HVAC-standard parameterization:
    - Proportional Band (K): temperature range over which output spans 0-100%.
      Converted to simple-pid Kp: Kp = 100 / proportional_band
    - Integral Time (min): time for integral action to repeat proportional action.
      Converted to simple-pid Ki: Ki = Kp / (integral_time_minutes * 60)

    Cooling mode is handled by negating gains (not the deviation), which keeps
    simple-pid's anti-windup working correctly.
    """

    # -------------------------------------------------------------------
    # hvac_to_pid_gains (static)
    # -------------------------------------------------------------------

    @staticmethod
    def hvac_to_pid_gains(
        proportional_band: float,
        integral_time_min: float,
    ) -> tuple[float, float]:
        """Convert HVAC-standard parameters to simple-pid Kp/Ki.

        Args:
            proportional_band: Proportional band in Kelvin. Must be > 0.
            integral_time_min: Integral time (reset time) in minutes. Must be > 0.

        Returns:
            Tuple of (Kp, Ki) for simple-pid.
        """

        kp = 100.0 / proportional_band
        ki = kp / (integral_time_min * 60.0)
        return kp, ki

    # -------------------------------------------------------------------
    # __init__
    # -------------------------------------------------------------------

    def __init__(
        self,
        proportional_band: float,
        integral_time_min: float,
        output_min: float,
        output_max: float,
        sample_time: float,
        setpoint: float = 0.0,
        is_cooling: bool = False,
    ) -> None:
        """Initialize the PI controller.

        Args:
            proportional_band: Proportional band in Kelvin (> 0).
            integral_time_min: Integral time in minutes (> 0).
            output_min: Minimum output percentage.
            output_max: Maximum output percentage.
            sample_time: Time between updates in seconds. Passed to simple-pid
                         so it can enforce minimum intervals between calculations.
            setpoint: Initial target temperature.
            is_cooling: If True, controller operates in cooling mode (negative gains).
        """

        kp, ki = self.hvac_to_pid_gains(proportional_band, integral_time_min)

        self._pid = PID(
            Kp=kp,
            Ki=ki,
            Kd=0,
            setpoint=setpoint,
            sample_time=sample_time,
            output_limits=(output_min, output_max),
        )

        self._is_cooling = is_cooling
        self._proportional_band = proportional_band
        self._integral_time_min = integral_time_min

        # Apply sign convention for cooling mode
        if is_cooling:
            self._apply_sign()

    # -------------------------------------------------------------------
    # _apply_sign
    # -------------------------------------------------------------------

    def _apply_sign(self) -> None:
        """Apply sign to gains based on current mode.

        Heating mode: positive gains (deviation = setpoint - current > 0 → positive output).
        Cooling mode: negative gains (deviation = setpoint - current < 0 → positive output).
        """

        if self._is_cooling:
            self._pid.Kp = -abs(self._pid.Kp)
            self._pid.Ki = -abs(self._pid.Ki)
        else:
            self._pid.Kp = abs(self._pid.Kp)
            self._pid.Ki = abs(self._pid.Ki)

    # -------------------------------------------------------------------
    # set_cooling
    # -------------------------------------------------------------------

    def set_cooling(self, is_cooling: bool) -> None:
        """Switch between heating and cooling mode at runtime.

        Used in heat_cool operating mode where the coordinator reads the climate
        entity's hvac_action and calls this method accordingly.

        Args:
            is_cooling: True for cooling mode, False for heating mode.
        """

        if is_cooling != self._is_cooling:
            self._is_cooling = is_cooling
            self._pid.reset()
            self._apply_sign()

    # -------------------------------------------------------------------
    # update
    # -------------------------------------------------------------------

    def update(self, current_temp: float, dt: float | None = None) -> PIResult:
        """Run one PI iteration.

        Args:
            current_temp: The current measured temperature.
            dt: Optional explicit timestep in seconds. If None, simple-pid uses
                real elapsed time since the last call.

        Returns:
            PIResult with the computed output and component values.
        """

        output = self._pid(current_temp, dt=dt)

        # simple-pid returns None if sample_time hasn't elapsed; treat as 0
        if output is None:
            output = 0.0

        p_term, i_term, _ = self._pid.components
        deviation = self._pid.setpoint - current_temp

        return PIResult(
            output=output,
            deviation=deviation,
            p_term=p_term,
            i_term=i_term,
        )

    # -------------------------------------------------------------------
    # set_target
    # -------------------------------------------------------------------

    def set_target(self, target: float) -> None:
        """Update the setpoint (target temperature).

        Args:
            target: The new target temperature.
        """

        self._pid.setpoint = target

    # -------------------------------------------------------------------
    # update_tunings
    # -------------------------------------------------------------------

    def update_tunings(
        self,
        proportional_band: float,
        integral_time_min: float,
    ) -> None:
        """Update gains at runtime. Accepts HVAC-standard units, converts internally.

        Args:
            proportional_band: New proportional band in Kelvin (> 0).
            integral_time_min: New integral time in minutes (> 0).
        """

        self._proportional_band = proportional_band
        self._integral_time_min = integral_time_min

        kp, ki = self.hvac_to_pid_gains(proportional_band, integral_time_min)
        self._pid.tunings = (kp, ki, 0)

        # Re-apply sign convention after tuning change
        self._apply_sign()

    # -------------------------------------------------------------------
    # update_output_limits
    # -------------------------------------------------------------------

    def update_output_limits(self, output_min: float, output_max: float) -> None:
        """Update output limits at runtime.

        Args:
            output_min: New minimum output percentage.
            output_max: New maximum output percentage.
        """

        self._pid.output_limits = (output_min, output_max)

    # -------------------------------------------------------------------
    # update_sample_time
    # -------------------------------------------------------------------

    def update_sample_time(self, sample_time: float) -> None:
        """Update the sample time (update interval).

        Args:
            sample_time: New sample time in seconds.
        """

        self._pid.sample_time = sample_time

    # -------------------------------------------------------------------
    # get_integral_term
    # -------------------------------------------------------------------

    def get_integral_term(self) -> float:
        """Return current integral term for persistence across restarts."""

        _, i_term, _ = self._pid.components
        return float(i_term)

    # -------------------------------------------------------------------
    # restore_integral_term
    # -------------------------------------------------------------------

    def restore_integral_term(self, value: float) -> None:
        """Restore integral term after restart.

        Uses the public ``set_auto_mode`` API: disable auto mode, then
        re-enable with the desired integral value as ``last_output``.

        Args:
            value: The integral term value to restore.
        """

        self._pid.set_auto_mode(False)
        self._pid.set_auto_mode(True, last_output=value)

    # -------------------------------------------------------------------
    # reset
    # -------------------------------------------------------------------

    def reset(self) -> None:
        """Reset the controller (clear integral term and internal state)."""

        self._pid.reset()

        # Re-apply sign convention since reset clears the gains to their absolute values
        self._apply_sign()

    # -------------------------------------------------------------------
    # Properties
    # -------------------------------------------------------------------

    @property
    def is_cooling(self) -> bool:
        """Whether the controller is in cooling mode."""

        return self._is_cooling

    @property
    def setpoint(self) -> float:
        """The current setpoint (target temperature)."""

        return float(self._pid.setpoint)

    @property
    def proportional_band(self) -> float:
        """The current proportional band in Kelvin."""

        return self._proportional_band

    @property
    def integral_time_min(self) -> float:
        """The current integral time in minutes."""

        return self._integral_time_min
