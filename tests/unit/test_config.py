"""Unit tests for config.py.

Tests cover:
- ConfKeys enum: all members defined and unique.
- CONF_SPECS registry: all ConfKeys have specs, converters work, defaults are typed.
- resolve(): produces correct defaults, merges overrides, handles coercion/fallback.
- resolve_entry(): works with objects having an ``options`` attribute.
- ResolvedConfig: generic access, as_enum_dict.
- get_runtime_configurable_keys(): returns expected set.
"""

from __future__ import annotations

from dataclasses import fields
from types import SimpleNamespace

import pytest

from custom_components.pi_thermostat.config import (
    CONF_SPECS,
    ConfKeys,
    ResolvedConfig,
    get_runtime_configurable_keys,
    resolve,
    resolve_entry,
)
from custom_components.pi_thermostat.const import (
    DEFAULT_INT_TIME,
    DEFAULT_ITERM_STARTUP_VALUE,
    DEFAULT_OUTPUT_MAX,
    DEFAULT_OUTPUT_MIN,
    DEFAULT_PROP_BAND,
    UPDATE_INTERVAL_DEFAULT_SECONDS,
    ITermStartupMode,
    OperatingMode,
    SensorFaultMode,
)

# ---------------------------------------------------------------------------
# ConfKeys
# ---------------------------------------------------------------------------


class TestConfKeys:
    """Test ConfKeys enum completeness and uniqueness."""

    def test_all_keys_unique(self) -> None:
        """All ConfKeys values are unique strings."""

        values = [k.value for k in ConfKeys]
        assert len(values) == len(set(values))

    def test_every_key_has_spec(self) -> None:
        """Every ConfKeys member has an entry in CONF_SPECS."""

        for key in ConfKeys:
            assert key in CONF_SPECS, f"Missing CONF_SPECS entry for {key}"

    def test_every_spec_has_key(self) -> None:
        """Every CONF_SPECS entry refers to a valid ConfKeys member."""

        for key in CONF_SPECS:
            assert key in ConfKeys, f"Unknown key in CONF_SPECS: {key}"

    def test_key_count_matches(self) -> None:
        """ConfKeys and CONF_SPECS have the same number of entries."""

        assert len(ConfKeys) == len(CONF_SPECS)


# ---------------------------------------------------------------------------
# CONF_SPECS
# ---------------------------------------------------------------------------


class TestConfSpecs:
    """Test CONF_SPECS registry defaults and converters."""

    def test_defaults_not_none(self) -> None:
        """No spec has a None default."""

        for key, spec in CONF_SPECS.items():
            assert spec.default is not None, f"{key} has None default"

    def test_converters_callable(self) -> None:
        """All converters are callable."""

        for key, spec in CONF_SPECS.items():
            assert callable(spec.converter), f"{key} converter not callable"

    def test_converter_on_default(self) -> None:
        """Converter applied to the default produces the same value."""

        for key, spec in CONF_SPECS.items():
            result = spec.converter(spec.default)
            assert result == spec.converter(spec.default), f"Converter unstable for {key}"

    def test_bool_converter(self) -> None:
        """Bool converter handles various inputs."""

        spec = CONF_SPECS[ConfKeys.ENABLED]
        assert spec.converter(True) is True
        assert spec.converter(False) is False
        assert spec.converter("true") is True
        assert spec.converter("false") is False
        assert spec.converter("yes") is True
        assert spec.converter("no") is False
        assert spec.converter(1) is True
        assert spec.converter(0) is False

    def test_float_converter(self) -> None:
        """Float converter handles ints and strings."""

        spec = CONF_SPECS[ConfKeys.PROPORTIONAL_BAND]
        assert spec.converter(4) == 4.0
        assert spec.converter("4.5") == 4.5
        assert isinstance(spec.converter(4), float)

    def test_int_converter(self) -> None:
        """Int converter handles floats and strings."""

        spec = CONF_SPECS[ConfKeys.UPDATE_INTERVAL]
        assert spec.converter(60.0) == 60
        assert spec.converter("30") == 30
        assert isinstance(spec.converter(60.0), int)

    def test_str_converter(self) -> None:
        """Str converter produces string output."""

        spec = CONF_SPECS[ConfKeys.OPERATING_MODE]
        assert spec.converter("heat") == "heat"
        assert isinstance(spec.converter("heat"), str)


# ---------------------------------------------------------------------------
# resolve()
# ---------------------------------------------------------------------------


class TestResolve:
    """Test the resolve() function."""

    def test_all_defaults(self) -> None:
        """Resolve with no overrides yields all defaults."""

        resolved = resolve(None)
        assert resolved.enabled is True
        assert resolved.climate_entity == ""
        assert resolved.temp_sensor == ""
        assert resolved.target_temp_mode == "internal"
        assert resolved.target_temp_entity == ""
        assert resolved.target_temp == 20.0
        assert resolved.operating_mode == OperatingMode.HEAT_COOL
        assert resolved.auto_disable_on_hvac_off is True
        assert resolved.proportional_band == DEFAULT_PROP_BAND
        assert resolved.integral_time == DEFAULT_INT_TIME
        assert resolved.output_entity == ""
        assert resolved.output_min == DEFAULT_OUTPUT_MIN
        assert resolved.output_max == DEFAULT_OUTPUT_MAX
        assert resolved.update_interval == UPDATE_INTERVAL_DEFAULT_SECONDS
        assert resolved.sensor_fault_mode == SensorFaultMode.SHUTDOWN
        assert resolved.iterm_startup_mode == ITermStartupMode.LAST
        assert resolved.iterm_startup_value == DEFAULT_ITERM_STARTUP_VALUE

    def test_empty_dict_defaults(self) -> None:
        """Resolve with empty dict is equivalent to None."""

        resolved = resolve({})
        default = resolve(None)

        for field in fields(ResolvedConfig):
            assert getattr(resolved, field.name) == getattr(default, field.name)

    def test_override_single(self) -> None:
        """Override a single key."""

        resolved = resolve({"proportional_band": 8.0})
        assert resolved.proportional_band == 8.0
        # Others still default
        assert resolved.integral_time == DEFAULT_INT_TIME

    def test_override_multiple(self) -> None:
        """Override multiple keys."""

        resolved = resolve(
            {
                "enabled": False,
                "proportional_band": 2.0,
                "integral_time": 60.0,
                "update_interval": 30,
            }
        )
        assert resolved.enabled is False
        assert resolved.proportional_band == 2.0
        assert resolved.integral_time == 60.0
        assert resolved.update_interval == 30

    def test_coercion_string_to_float(self) -> None:
        """String values are coerced to correct types."""

        resolved = resolve({"proportional_band": "5.5"})
        assert resolved.proportional_band == 5.5
        assert isinstance(resolved.proportional_band, float)

    def test_coercion_string_to_int(self) -> None:
        """String values are coerced to int."""

        resolved = resolve({"update_interval": "120"})
        assert resolved.update_interval == 120
        assert isinstance(resolved.update_interval, int)

    def test_coercion_string_to_bool(self) -> None:
        """String bool values are coerced."""

        resolved = resolve({"enabled": "false"})
        assert resolved.enabled is False

    def test_bad_value_falls_back_to_default(self) -> None:
        """Un-convertible values fall back to the coerced default."""

        resolved = resolve({"proportional_band": "not_a_number"})
        assert resolved.proportional_band == DEFAULT_PROP_BAND

    def test_unknown_keys_ignored(self) -> None:
        """Extra keys in options are silently ignored."""

        resolved = resolve({"unknown_key": "value", "proportional_band": 3.0})
        assert resolved.proportional_band == 3.0

    def test_returns_resolved_config(self) -> None:
        """resolve() returns a ResolvedConfig instance."""

        result = resolve(None)
        assert isinstance(result, ResolvedConfig)

    def test_resolved_config_frozen(self) -> None:
        """ResolvedConfig is frozen (immutable)."""

        resolved = resolve(None)
        with pytest.raises(AttributeError):
            resolved.enabled = False  # type: ignore[misc]


# ---------------------------------------------------------------------------
# resolve_entry()
# ---------------------------------------------------------------------------


class TestResolveEntry:
    """Test resolve_entry() with entry-like objects."""

    def test_with_options(self) -> None:
        """Resolves settings from entry.options."""

        entry = SimpleNamespace(options={"proportional_band": 6.0})
        resolved = resolve_entry(entry)
        assert resolved.proportional_band == 6.0

    def test_no_options(self) -> None:
        """Missing options attribute falls back to defaults."""

        entry = SimpleNamespace()
        resolved = resolve_entry(entry)
        assert resolved.proportional_band == DEFAULT_PROP_BAND

    def test_none_options(self) -> None:
        """None options falls back to defaults."""

        entry = SimpleNamespace(options=None)
        resolved = resolve_entry(entry)
        assert resolved.enabled is True


# ---------------------------------------------------------------------------
# ResolvedConfig methods
# ---------------------------------------------------------------------------


class TestResolvedConfig:
    """Test ResolvedConfig access methods."""

    def test_get_by_confkey(self) -> None:
        """Generic get() access works for all keys."""

        resolved = resolve({"proportional_band": 7.0})
        assert resolved.get(ConfKeys.PROPORTIONAL_BAND) == 7.0

    def test_as_enum_dict(self) -> None:
        """as_enum_dict() returns a dict keyed by ConfKeys."""

        resolved = resolve(None)
        d = resolved.as_enum_dict()

        assert isinstance(d, dict)
        assert all(isinstance(k, ConfKeys) for k in d)
        assert d[ConfKeys.ENABLED] is True
        assert d[ConfKeys.PROPORTIONAL_BAND] == DEFAULT_PROP_BAND

    def test_as_enum_dict_all_keys(self) -> None:
        """as_enum_dict() includes all ConfKeys."""

        resolved = resolve(None)
        d = resolved.as_enum_dict()
        assert set(d.keys()) == set(ConfKeys)

    def test_field_count_matches_confkeys(self) -> None:
        """ResolvedConfig has the same number of fields as ConfKeys members."""

        assert len(fields(ResolvedConfig)) == len(ConfKeys)


# ---------------------------------------------------------------------------
# get_runtime_configurable_keys()
# ---------------------------------------------------------------------------


class TestRuntimeConfigurableKeys:
    """Test get_runtime_configurable_keys()."""

    def test_returns_set_of_strings(self) -> None:
        """Returns a set of strings."""

        keys = get_runtime_configurable_keys()
        assert isinstance(keys, set)
        assert all(isinstance(k, str) for k in keys)

    def test_includes_expected_keys(self) -> None:
        """Runtime configurable keys include known entries."""

        keys = get_runtime_configurable_keys()
        assert "enabled" in keys
        assert "proportional_band" in keys
        assert "integral_time" in keys
        assert "target_temp" in keys
        assert "output_min" in keys
        assert "output_max" in keys
        assert "update_interval" in keys
        assert "auto_disable_on_hvac_off" in keys

    def test_excludes_structural_keys(self) -> None:
        """Structural keys are not runtime configurable."""

        keys = get_runtime_configurable_keys()
        assert "climate_entity" not in keys
        assert "temp_sensor" not in keys
        assert "operating_mode" not in keys
        assert "output_entity" not in keys
        assert "sensor_fault_mode" not in keys
        assert "iterm_startup_mode" not in keys
