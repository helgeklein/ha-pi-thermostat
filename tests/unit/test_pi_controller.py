"""Unit tests for PIController and PIResult.

Tests cover:
- HVAC-to-PID gain conversion
- Heating mode: cold start, steady state, overshoot
- Cooling mode: warm room cooling down
- Output clamping to configured limits
- Anti-windup (integral doesn't grow when output is saturated)
- Mode switching (heat ↔ cool)
- Setpoint changes
- Tuning changes at runtime
- Output limit changes at runtime
- Integral term save/restore (persistence)
- Controller reset
- Sample time updates
"""

from __future__ import annotations

from typing import Any

import pytest

from tests.unit.conftest import import_module_direct

_mod = import_module_direct("pi_controller")
PIController = _mod.PIController  # type: ignore[attr-defined]
PIResult = _mod.PIResult  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Standard test parameters
TEST_PROP_BAND = 4.0  # 4 K proportional band → Kp = 25
TEST_INT_TIME = 30.0  # 30 min integral time → Ki ≈ 0.01389
TEST_OUTPUT_MIN = 0.0
TEST_OUTPUT_MAX = 100.0
TEST_SAMPLE_TIME = 60.0  # 60 seconds
TEST_SETPOINT = 21.0


@pytest.fixture()
def heating_controller() -> Any:
    """Create a PI controller in heating mode with standard test parameters."""

    return PIController(
        proportional_band=TEST_PROP_BAND,
        integral_time_min=TEST_INT_TIME,
        output_min=TEST_OUTPUT_MIN,
        output_max=TEST_OUTPUT_MAX,
        sample_time=TEST_SAMPLE_TIME,
        setpoint=TEST_SETPOINT,
        is_cooling=False,
    )


@pytest.fixture()
def cooling_controller() -> Any:
    """Create a PI controller in cooling mode with standard test parameters."""

    return PIController(
        proportional_band=TEST_PROP_BAND,
        integral_time_min=TEST_INT_TIME,
        output_min=TEST_OUTPUT_MIN,
        output_max=TEST_OUTPUT_MAX,
        sample_time=TEST_SAMPLE_TIME,
        setpoint=TEST_SETPOINT,
        is_cooling=True,
    )


# ---------------------------------------------------------------------------
# HVAC-to-PID gain conversion
# ---------------------------------------------------------------------------


class TestHvacToPidGains:
    """Tests for the HVAC-standard to simple-pid gain conversion."""

    def test_standard_conversion(self) -> None:
        """4 K band, 30 min integral time → Kp=25, Ki≈0.01389."""

        kp, ki = PIController.hvac_to_pid_gains(4.0, 30.0)

        assert kp == pytest.approx(25.0)
        assert ki == pytest.approx(25.0 / (30.0 * 60.0))

    def test_narrow_band_high_gain(self) -> None:
        """Narrow band → higher Kp (more aggressive)."""

        kp, _ = PIController.hvac_to_pid_gains(2.0, 30.0)

        assert kp == pytest.approx(50.0)

    def test_wide_band_low_gain(self) -> None:
        """Wide band → lower Kp (less aggressive)."""

        kp, _ = PIController.hvac_to_pid_gains(10.0, 30.0)

        assert kp == pytest.approx(10.0)

    def test_short_integral_time_high_ki(self) -> None:
        """Short integral time → higher Ki (faster integral response)."""

        _, ki_short = PIController.hvac_to_pid_gains(4.0, 10.0)
        _, ki_long = PIController.hvac_to_pid_gains(4.0, 60.0)

        assert ki_short > ki_long

    def test_integral_time_relationship(self) -> None:
        """Ki = Kp / (integral_time_min * 60)."""

        kp, ki = PIController.hvac_to_pid_gains(5.0, 45.0)

        assert ki == pytest.approx(kp / (45.0 * 60.0))


# ---------------------------------------------------------------------------
# PIResult
# ---------------------------------------------------------------------------


class TestPIResult:
    """Tests for the PIResult dataclass."""

    def test_frozen(self) -> None:
        """PIResult should be immutable."""

        result = PIResult(output=50.0, error=2.5, p_term=45.0, i_term=5.0)

        with pytest.raises(AttributeError):
            result.output = 99.0  # type: ignore[misc]

    def test_values(self) -> None:
        """PIResult stores values correctly."""

        result = PIResult(output=75.0, error=3.0, p_term=60.0, i_term=15.0)

        assert result.output == 75.0
        assert result.error == 3.0
        assert result.p_term == 60.0
        assert result.i_term == 15.0


# ---------------------------------------------------------------------------
# Heating mode
# ---------------------------------------------------------------------------


class TestHeatingMode:
    """Tests for the controller in heating mode."""

    def test_cold_start_positive_output(self, heating_controller: Any) -> None:
        """When current temp is well below setpoint, output should be high."""

        # 18°C current, 21°C target → 3°C error, Kp=25 → P=75
        result = heating_controller.update(18.0, dt=TEST_SAMPLE_TIME)

        assert result.output > 0
        assert result.error == pytest.approx(3.0)
        assert result.p_term > 0

    def test_at_setpoint_low_output(self, heating_controller: Any) -> None:
        """When current temp equals setpoint, proportional term should be ~0."""

        result = heating_controller.update(TEST_SETPOINT, dt=TEST_SAMPLE_TIME)

        assert result.p_term == pytest.approx(0.0, abs=0.1)

    def test_above_setpoint_zero_output(self, heating_controller: Any) -> None:
        """When current temp is above setpoint in heating mode, output should be 0 (clamped)."""

        # 23°C > 21°C setpoint → negative error → output clamped to 0
        result = heating_controller.update(23.0, dt=TEST_SAMPLE_TIME)

        assert result.output == pytest.approx(0.0)

    def test_output_ramps_with_integral(self, heating_controller: Any) -> None:
        """Multiple iterations at constant error should increase output via integral."""

        results = []
        for _ in range(5):
            results.append(heating_controller.update(19.0, dt=TEST_SAMPLE_TIME))

        # Integral should grow over iterations
        assert results[-1].i_term > results[0].i_term

    def test_error_sign_heating(self, heating_controller: Any) -> None:
        """In heating mode, error = setpoint - current (positive when cold)."""

        result = heating_controller.update(18.0, dt=TEST_SAMPLE_TIME)

        assert result.error == pytest.approx(3.0)


# ---------------------------------------------------------------------------
# Cooling mode
# ---------------------------------------------------------------------------


class TestCoolingMode:
    """Tests for the controller in cooling mode."""

    def test_warm_room_positive_output(self, cooling_controller: Any) -> None:
        """When current temp is above setpoint in cooling mode, output should be positive."""

        # 25°C current, 21°C target → room is too warm → needs cooling
        result = cooling_controller.update(25.0, dt=TEST_SAMPLE_TIME)

        assert result.output > 0

    def test_cold_room_zero_output(self, cooling_controller: Any) -> None:
        """When current temp is below setpoint in cooling mode, output should be 0."""

        # 18°C < 21°C → no cooling needed → output clamped to 0
        result = cooling_controller.update(18.0, dt=TEST_SAMPLE_TIME)

        assert result.output == pytest.approx(0.0)

    def test_gains_are_negative(self, cooling_controller: Any) -> None:
        """In cooling mode, Kp and Ki should be negative."""

        assert cooling_controller._pid.Kp < 0
        assert cooling_controller._pid.Ki < 0


# ---------------------------------------------------------------------------
# Output clamping
# ---------------------------------------------------------------------------


class TestOutputClamping:
    """Tests for output limit enforcement."""

    def test_output_never_exceeds_max(self, heating_controller: Any) -> None:
        """Output should never exceed output_max even with large error."""

        # Very cold room: 5°C, setpoint 21°C → 16°C error → P alone = 400, but max is 100
        result = heating_controller.update(5.0, dt=TEST_SAMPLE_TIME)

        assert result.output <= TEST_OUTPUT_MAX

    def test_output_never_below_min(self, heating_controller: Any) -> None:
        """Output should never go below output_min."""

        # Very warm room in heating mode → output should be 0, not negative
        result = heating_controller.update(30.0, dt=TEST_SAMPLE_TIME)

        assert result.output >= TEST_OUTPUT_MIN

    def test_custom_limits(self) -> None:
        """Custom output limits should be respected."""

        controller = PIController(
            proportional_band=TEST_PROP_BAND,
            integral_time_min=TEST_INT_TIME,
            output_min=20.0,
            output_max=80.0,
            sample_time=TEST_SAMPLE_TIME,
            setpoint=TEST_SETPOINT,
        )

        # Large error → output clamped to 80
        result = controller.update(5.0, dt=TEST_SAMPLE_TIME)
        assert result.output <= 80.0

        # Negative error → output clamped to 20
        result = controller.update(30.0, dt=TEST_SAMPLE_TIME)
        assert result.output >= 20.0


# ---------------------------------------------------------------------------
# Anti-windup
# ---------------------------------------------------------------------------


class TestAntiWindup:
    """Tests for integral anti-windup behavior."""

    def test_integral_does_not_grow_when_saturated(self, heating_controller: Any) -> None:
        """When output is at max, integral should not keep growing."""

        # Drive output to saturation with very cold temperature
        for _ in range(20):
            heating_controller.update(5.0, dt=TEST_SAMPLE_TIME)

        i_term_saturated = heating_controller.get_integral_term()

        # Continue at saturation
        for _ in range(20):
            heating_controller.update(5.0, dt=TEST_SAMPLE_TIME)

        i_term_after = heating_controller.get_integral_term()

        # Integral should not have grown significantly beyond the saturation point
        # Allow a small tolerance since clamping might not be perfectly tight
        assert i_term_after == pytest.approx(i_term_saturated, abs=1.0)


# ---------------------------------------------------------------------------
# Mode switching
# ---------------------------------------------------------------------------


class TestModeSwitching:
    """Tests for switching between heating and cooling modes."""

    def test_switch_to_cooling(self, heating_controller: Any) -> None:
        """Switching to cooling should negate gains."""

        assert heating_controller._pid.Kp > 0

        heating_controller.set_cooling(True)

        assert heating_controller._pid.Kp < 0
        assert heating_controller.is_cooling is True

    def test_switch_to_heating(self, cooling_controller: Any) -> None:
        """Switching to heating should make gains positive."""

        assert cooling_controller._pid.Kp < 0

        cooling_controller.set_cooling(False)

        assert cooling_controller._pid.Kp > 0
        assert cooling_controller.is_cooling is False

    def test_no_op_same_mode(self, heating_controller: Any) -> None:
        """Setting the same mode should be a no-op."""

        kp_before = heating_controller._pid.Kp
        heating_controller.set_cooling(False)

        assert heating_controller._pid.Kp == kp_before

    def test_cooling_output_after_switch(self, heating_controller: Any) -> None:
        """After switching to cooling, warm room should produce positive output."""

        heating_controller.set_cooling(True)
        result = heating_controller.update(25.0, dt=TEST_SAMPLE_TIME)

        assert result.output > 0


# ---------------------------------------------------------------------------
# Setpoint changes
# ---------------------------------------------------------------------------


class TestSetpointChanges:
    """Tests for runtime setpoint changes."""

    def test_set_target(self, heating_controller: Any) -> None:
        """Changing the setpoint should be reflected in the controller."""

        heating_controller.set_target(25.0)

        assert heating_controller.setpoint == 25.0

    def test_output_adapts_to_new_setpoint(self, heating_controller: Any) -> None:
        """After raising the setpoint, output should increase for the same current temp."""

        result_before = heating_controller.update(20.0, dt=TEST_SAMPLE_TIME)

        heating_controller.set_target(25.0)
        result_after = heating_controller.update(20.0, dt=TEST_SAMPLE_TIME)

        assert result_after.output > result_before.output


# ---------------------------------------------------------------------------
# Tuning changes
# ---------------------------------------------------------------------------


class TestTuningChanges:
    """Tests for runtime tuning parameter changes."""

    def test_update_tunings(self, heating_controller: Any) -> None:
        """Tuning changes should be reflected in the controller."""

        heating_controller.update_tunings(8.0, 60.0)

        assert heating_controller.proportional_band == 8.0
        assert heating_controller.integral_time_min == 60.0

    def test_narrower_band_increases_output(self, heating_controller: Any) -> None:
        """Narrower proportional band → higher gain → higher output for same error."""

        result_wide = heating_controller.update(19.0, dt=TEST_SAMPLE_TIME)

        # Create a fresh controller with narrower band
        narrow = PIController(
            proportional_band=2.0,
            integral_time_min=TEST_INT_TIME,
            output_min=TEST_OUTPUT_MIN,
            output_max=TEST_OUTPUT_MAX,
            sample_time=TEST_SAMPLE_TIME,
            setpoint=TEST_SETPOINT,
        )
        result_narrow = narrow.update(19.0, dt=TEST_SAMPLE_TIME)

        assert result_narrow.p_term > result_wide.p_term

    def test_cooling_sign_preserved_after_tuning(self, cooling_controller: Any) -> None:
        """Tuning change in cooling mode should keep gains negative."""

        cooling_controller.update_tunings(8.0, 60.0)

        assert cooling_controller._pid.Kp < 0
        assert cooling_controller._pid.Ki < 0


# ---------------------------------------------------------------------------
# Output limit changes
# ---------------------------------------------------------------------------


class TestOutputLimitChanges:
    """Tests for runtime output limit changes."""

    def test_update_output_limits(self, heating_controller: Any) -> None:
        """New output limits should be applied."""

        heating_controller.update_output_limits(10.0, 90.0)

        assert heating_controller._pid.output_limits == (10.0, 90.0)

    def test_output_respects_new_limits(self, heating_controller: Any) -> None:
        """Output should respect newly set limits."""

        heating_controller.update_output_limits(10.0, 50.0)

        # Large error → should be clamped to new max of 50
        result = heating_controller.update(5.0, dt=TEST_SAMPLE_TIME)

        assert result.output <= 50.0


# ---------------------------------------------------------------------------
# Sample time changes
# ---------------------------------------------------------------------------


class TestSampleTimeChanges:
    """Tests for runtime sample time changes."""

    def test_update_sample_time(self, heating_controller: Any) -> None:
        """Sample time should be updated on the underlying PID."""

        heating_controller.update_sample_time(120.0)

        assert heating_controller._pid.sample_time == 120.0


# ---------------------------------------------------------------------------
# Integral persistence
# ---------------------------------------------------------------------------


class TestIntegralPersistence:
    """Tests for integral term save/restore (for HA restart persistence)."""

    def test_get_integral_term(self, heating_controller: Any) -> None:
        """After some iterations, integral term should be retrievable."""

        heating_controller.update(19.0, dt=TEST_SAMPLE_TIME)

        i_term = heating_controller.get_integral_term()

        assert i_term > 0

    def test_restore_integral_term(self, heating_controller: Any) -> None:
        """Restoring an integral term should affect subsequent output."""

        # Run one iteration at setpoint to establish baseline
        result_baseline = heating_controller.update(TEST_SETPOINT, dt=TEST_SAMPLE_TIME)

        # Reset and restore a large integral term
        heating_controller.reset()
        heating_controller.restore_integral_term(30.0)

        result_restored = heating_controller.update(TEST_SETPOINT, dt=TEST_SAMPLE_TIME)

        # The restored integral should make the output higher than baseline
        assert result_restored.output > result_baseline.output

    def test_roundtrip_integral(self, heating_controller: Any) -> None:
        """Save and restore should produce the same integral value."""

        # Build up some integral
        for _ in range(5):
            heating_controller.update(19.0, dt=TEST_SAMPLE_TIME)

        saved = heating_controller.get_integral_term()

        # Create a new controller and restore
        new_controller = PIController(
            proportional_band=TEST_PROP_BAND,
            integral_time_min=TEST_INT_TIME,
            output_min=TEST_OUTPUT_MIN,
            output_max=TEST_OUTPUT_MAX,
            sample_time=TEST_SAMPLE_TIME,
            setpoint=TEST_SETPOINT,
        )
        new_controller.restore_integral_term(saved)

        assert new_controller.get_integral_term() == pytest.approx(saved)


# ---------------------------------------------------------------------------
# Reset
# ---------------------------------------------------------------------------


class TestReset:
    """Tests for controller reset."""

    def test_reset_clears_integral(self, heating_controller: Any) -> None:
        """Reset should clear the integral term."""

        # Build up integral
        for _ in range(5):
            heating_controller.update(19.0, dt=TEST_SAMPLE_TIME)

        assert heating_controller.get_integral_term() > 0

        heating_controller.reset()

        assert heating_controller.get_integral_term() == pytest.approx(0.0)

    def test_reset_preserves_cooling_sign(self, cooling_controller: Any) -> None:
        """Reset should preserve the cooling mode sign convention."""

        cooling_controller.update(25.0, dt=TEST_SAMPLE_TIME)
        cooling_controller.reset()

        assert cooling_controller._pid.Kp < 0
        assert cooling_controller._pid.Ki < 0


# ---------------------------------------------------------------------------
# Properties
# ---------------------------------------------------------------------------


class TestProperties:
    """Tests for read-only properties."""

    def test_is_cooling(self, heating_controller: Any, cooling_controller: Any) -> None:
        """is_cooling property should reflect the controller's mode."""

        assert heating_controller.is_cooling is False
        assert cooling_controller.is_cooling is True

    def test_setpoint(self, heating_controller: Any) -> None:
        """setpoint property should reflect the current target."""

        assert heating_controller.setpoint == TEST_SETPOINT

        heating_controller.set_target(25.0)

        assert heating_controller.setpoint == 25.0

    def test_proportional_band(self, heating_controller: Any) -> None:
        """proportional_band property should reflect the current value."""

        assert heating_controller.proportional_band == TEST_PROP_BAND

    def test_integral_time_min(self, heating_controller: Any) -> None:
        """integral_time_min property should reflect the current value."""

        assert heating_controller.integral_time_min == TEST_INT_TIME
