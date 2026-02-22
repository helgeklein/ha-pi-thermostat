"""Tests for util.py.

Tests cover:
- to_float_or_none: int, float, numeric string, non-numeric string, None, other types.
- to_int_or_none: int, float, numeric string, non-numeric string, None, other types.
"""

from __future__ import annotations

import pytest

from custom_components.pi_thermostat.util import to_float_or_none, to_int_or_none

# ===========================================================================
# to_float_or_none
# ===========================================================================


class TestToFloatOrNone:
    """Test to_float_or_none coercion helper."""

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            (42, 42.0),
            (0, 0.0),
            (-7, -7.0),
            (3.14, 3.14),
            (-0.5, -0.5),
            ("10.5", 10.5),
            ("0", 0.0),
            ("-3", -3.0),
        ],
    )
    def test_valid_values(self, raw: object, expected: float) -> None:
        """Numeric ints, floats, and strings are coerced to float."""

        assert to_float_or_none(raw) == pytest.approx(expected)

    @pytest.mark.parametrize(
        "raw",
        [
            "not_a_number",
            "",
        ],
    )
    def test_non_numeric_string_returns_none(self, raw: str) -> None:
        """Non-numeric strings return None."""

        assert to_float_or_none(raw) is None

    @pytest.mark.parametrize(
        "raw",
        [
            None,
            [],
            {},
            object(),
        ],
    )
    def test_non_coercible_types_return_none(self, raw: object) -> None:
        """None, lists, dicts, and other non-numeric types return None."""

        assert to_float_or_none(raw) is None


# ===========================================================================
# to_int_or_none
# ===========================================================================


class TestToIntOrNone:
    """Test to_int_or_none coercion helper."""

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            (42, 42),
            (0, 0),
            (-7, -7),
            (3.9, 3),  # truncated, not rounded
            (-2.1, -2),
            ("10", 10),
            ("0", 0),
            ("-3", -3),
        ],
    )
    def test_valid_values(self, raw: object, expected: int) -> None:
        """Numeric ints, floats, and strings are coerced to int."""

        assert to_int_or_none(raw) == expected

    @pytest.mark.parametrize(
        "raw",
        [
            "not_a_number",
            "",
            "3.14",  # int() rejects float-formatted strings
        ],
    )
    def test_non_numeric_string_returns_none(self, raw: str) -> None:
        """Non-numeric or float-formatted strings return None."""

        assert to_int_or_none(raw) is None

    @pytest.mark.parametrize(
        "raw",
        [
            None,
            [],
            {},
            object(),
        ],
    )
    def test_non_coercible_types_return_none(self, raw: object) -> None:
        """None, lists, dicts, and other non-numeric types return None."""

        assert to_int_or_none(raw) is None
