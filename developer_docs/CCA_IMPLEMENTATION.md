# CCA Mode Implementation Notes

This document is for maintainers. User-facing setup, tuning guidance, and runtime-entity descriptions live in the public docs.

## Code Ownership

The main implementation surfaces are:

- `custom_components/pi_thermostat/config.py`
  - typed config resolution, defaults, and runtime-configurable key registry
- `custom_components/pi_thermostat/config_flow.py`
  - mode-aware options flow
- `custom_components/pi_thermostat/coordinator.py`
  - shared update coordinator, mode dispatch, CCA scheduling, runtime refresh handling, and CCA state persistence
- `custom_components/pi_thermostat/cca_controller.py`
  - CCA control algorithm and persisted CCA state model
- `custom_components/pi_thermostat/ha_interface.py`
  - Home Assistant weather, climate, and generic entity access helpers
- `custom_components/pi_thermostat/number.py`, `switch.py`, `sensor.py`
  - conditional PI and CCA entities

## Configuration Behavior

All user configuration is stored in config entry options and resolved through `ResolvedConfig`.

### Structural CCA settings

- `control_mode`
- `cca_cooling_enable_entity`
- `cca_cooling_enable_on`
- `cca_weather_entity`
- `cca_forecast_horizon_days`
- `cca_forecast_unavailable_mode`

Changing these settings causes a full integration reload.

### Runtime-configurable CCA settings

- `enabled`
- `cca_update_interval_minutes`
- `cca_manual_override_enabled`
- `cca_manual_output`
- `cca_hot_day_threshold`
- `cca_warm_night_threshold`
- `cca_output_min`
- `cca_output_max`
- `cca_forecast_response_strength`
- `cca_thermal_storage_persistence`
- `cca_output_step_limit`
- `cca_charge_target_scale`

These settings are exposed through entities and persist via config entry options. Changing them triggers a coordinator refresh instead of a full reload.

## Persisted State and Restore Contract

CCA runtime state is persisted through Home Assistant `Store`, not through a `RestoreEntity` carrier.

The persisted `CCAState` fields are:

- `charge_estimate`
- `last_auto_output`
- `last_heat_score`
- `last_step_timestamp_iso`
- `status`

Default first-start state is:

- `charge_estimate = 0.0`
- `last_auto_output = 0.0`
- `last_heat_score = 0.0`
- `last_step_timestamp_iso = None`
- `status = "idle"`

### Persistence mechanism

- config and runtime settings persist in config entry options
- PI integral state persists through the `i_term` sensor's `RestoreEntity` behavior
- CCA runtime state persists through coordinator-managed storage under a per-entry key

### Startup order

On setup:

1. the coordinator is created
2. stored CCA state is restored when `control_mode == cca`
3. platforms are set up
4. the first coordinator refresh runs

### Restore normalization

Stored CCA state is validated and normalized during restore:

- `charge_estimate`, `last_auto_output`, and `last_heat_score` are clamped to `0..100`
- `status` must be one of `idle`, `inactive`, `forecast_hold`, `forecast_unavailable`, `active`, or `manual_override`
- `last_step_timestamp_iso` must be a valid ISO timestamp

If normalization changes the stored payload, the normalized state is written back immediately.

## Scheduling and Refresh Semantics

CCA uses two time concepts:

- coordinator heartbeat: fixed at 60 seconds
- automatic CCA control interval: `cca_update_interval_minutes`

The coordinator wakes up every minute in CCA mode, but a new automatic CCA control step is only computed when the elapsed time since `last_step_timestamp_iso` reaches the configured CCA interval.

Runtime CCA setting changes are applied without consuming the next scheduled automatic CCA step.

During such refreshes, the coordinator may normalize cached CCA state immediately:

- clear stale `manual_override` state when manual override is turned off
- clamp cached `last_auto_output` to current `cca_output_min` and `cca_output_max`
- persist the normalized cached state before returning the refresh result

Some forecast-driven tuning changes, including `cca_charge_target_scale`, also trigger an immediate forecast-backed recompute of `last_auto_output`.

That recompute updates the current automatic output and published sensors immediately, but it does not advance `charge_estimate` and does not reset `last_step_timestamp_iso`.

## Forecast Handling Contract

Forecast handling is split between `ha_interface.py` and `cca_controller.py`.

### Home Assistant interface responsibilities

- validate that the configured weather entity exists
- validate support for daily forecasts
- call Home Assistant's weather forecast service
- return only dictionary forecast entries

### CCA controller responsibilities

- accept either `datetime` or `date`
- accept ISO timestamps with trailing `Z`
- ignore malformed forecast entries
- sort valid forecast entries by date
- limit the list to `cca_forecast_horizon_days`

If no valid forecasts remain, the controller falls back to the configured forecast-unavailable behavior.

## Internal Algorithm Reference

The current implementation uses a normalized `0..100` internal model.

### Heat score

For each valid forecast day:

- `hot_day_score = clip((high - cca_hot_day_threshold) * 12.5, 0, 100)`
- `warm_night_score = clip((low - cca_warm_night_threshold) * 20.0, 0, 100)`
- `daily_score = clip(hot_day_score * 0.7 + warm_night_score * 0.3, 0, 100)`

The final `heat_score` is the mean of all valid daily scores.

### Charge target

`charge_target = clip(heat_score * (cca_charge_target_scale / 100), 0, 100)`

### Derived gains from high-level sliders

The UI exposes two higher-level sliders:

- `cca_forecast_response_strength`
- `cca_thermal_storage_persistence`

These sliders are resolved into internal gains during config resolution.

Let:

- `response_scale = cca_forecast_response_strength / 100`
- `persistence_scale = cca_thermal_storage_persistence / 100`

Then the internal gains are derived as:

- `cca_charge_gain = clip(25 / persistence_scale, 10, 40)`
- `cca_discharge_gain = clip(20 * response_scale / persistence_scale, 8, 40)`

This preserves the previous baseline at `100 / 100`, which yields the historical defaults `cca_charge_gain = 25` and `cca_discharge_gain = 20`.

### Charge estimate update

`charge_estimate = clip(previous_charge_estimate + cca_charge_gain * (last_auto_output / 100) - cca_discharge_gain * (heat_score / 100), 0, 100)`

### Automatic output

- `requested_output = clip(charge_target - charge_estimate, 0, 100)`
- the automatic output may only change by `cca_output_step_limit` per automatic update
- automatic output is then clamped to `0..100`
- when automatic output is above zero, it is additionally clamped to `cca_output_min..cca_output_max`

### Manual override

When `cca_manual_override_enabled` is on:

- published output becomes `cca_manual_output` clamped to `0..100`
- `override_active` becomes `on`
- controller `status` becomes `manual_override`

The persisted `last_auto_output` still tracks the automatic basis rather than the manual output.

## Published State Contract

The main CCA statuses are:

- `idle`
- `inactive`
- `forecast_hold`
- `forecast_unavailable`
- `active`
- `manual_override`

Important published-state behaviors:

- when cooling is disabled, output is forced to `0` and status is `inactive`
- when forecast data is unavailable in `hold` mode, the last automatic output is reused and status is `forecast_hold`
- when forecast data is unavailable in `shutdown` mode, output is `0` and status is `forecast_unavailable`
- `cca_charge_target` is derived and published even on cached-refresh, inactive, and forecast-unavailable paths
- `cca_next_update_in` is only shown while cooling is enabled

## Related PI Persistence Note

PI mode uses a different persistence model:

- most PI settings persist through config entry options
- the integral term is restored by the `i_term` sensor via `RestoreEntity`
- on startup with missing controller inputs and `sensor_fault_mode = hold`, the coordinator returns `output = None` until it has a prior good PI output to hold

## Current Limitations

- CCA persistence is internal coordinator storage only; there is no dedicated hidden CCA restore entity
- forecast-unavailable behavior supports only `hold` and `shutdown`
- the CCA controller is based on daily highs and lows only; it does not use hourly forecasts or per-day weighting beyond the unweighted average
- the UI exposes higher-level slider controls, but the controller still runs on derived internal gains rather than directly on physical time constants or energy units

## Testing Expectations

The current test suite includes coverage for:

- CCA forecast parsing and scoring behavior
- mode-specific entity creation
- CCA state restore from storage
- restore normalization for invalid persisted CCA state
- cached refresh behavior and runtime-setting refresh behavior
- manual override behavior
- output clamps and step limiting
- CCA scheduling based on `cca_update_interval_minutes`

Update this document when implementation contracts or formulas change.