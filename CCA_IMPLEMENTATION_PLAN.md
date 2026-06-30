# CCA Mode Implementation Plan

## Purpose

This document captures the proposed design for extending the integration with a second control strategy for concrete core activation (CCA) cooling.

The goal is to make the design reviewable before implementation. No code changes are described here as final until reviewed.

## Summary

The integration should support two controller modes:

- `pi`: the existing room-temperature-based PI controller
- `cca`: a new forecast-driven supervisory controller for concrete core activation cooling

The controller mode is selected in the options flow as a new first step.

CCA mode is intentionally not a variant of the PI controller. It is a separate control strategy with different inputs, dynamics, persistence needs, and runtime controls.

## Goals

- Keep the existing PI behavior unchanged for current users.
- Add CCA as a second controller mode within the same integration.
- Use long-term weather forecast data instead of indoor room temperature in CCA mode.
- Only allow CCA output when the heat pump is in cooling mode.
- Support manual override of the CCA output.
- Persist CCA runtime status across Home Assistant restarts so the controller can resume where it left off.
- Expose the resulting CCA valve position as a percentage output.

## Non-Goals

- Do not merge CCA logic into the existing PI controller implementation.
- Do not make forecast-dependent control available in PI mode.
- Do not put day-to-day CCA tuning into the options flow.
- Do not require room temperature as an input for CCA control.

## Constraints

### Functional constraints

- CCA is supplemental cooling, not the primary cooling method.
- CCA has a slow response due to building thermal mass.
- CCA should only operate when the heat pump is actively in cooling mode.
- CCA should use longer-term forecast information.

### UX constraints

- Users must be able to switch between PI mode and CCA mode.
- The best place for the mode choice is the options flow.
- The options flow gets a new step 1, pushing the current steps 1 to 3 to steps 2 to 4.
- The following should not be configured in the options flow. They should be configured via the integration instance's settings entities only:
  - manual override
  - temperature thresholds
  - output limits
  - slow-state tuning

### Technical constraints

- Existing integration instances must continue to work without behavior changes.
- CCA state must survive Home Assistant restarts.
- Weather forecast interpretation should follow the same overall pattern used by the Smart Cover Automation integration.

## Source For Weather Forecast Handling

The Smart Cover Automation source can be found here:

- <https://github.com/helgeklein/ha-smart-cover-automation>

Relevant forecast-handling behavior already observed from that project and from local coverage artifacts:

- forecast support is validated during configuration
- weather forecast retrieval uses Home Assistant's weather forecast service
- daily forecast support is explicitly checked
- forecast entries may use either `datetime` or `date`
- ISO timestamps with trailing `Z` are parsed correctly
- malformed forecast entries are skipped rather than breaking the whole calculation

This integration should reuse the same approach conceptually, even if the exact code is adapted rather than copied.

## High-Level Architecture

The integration should become a two-strategy controller with one shared Home Assistant integration surface.

### Shared outer structure

- one config entry per integration instance
- one coordinator per instance
- one shared output contract: output percentage

### Controller strategies

- `PIControllerStrategy`
  - preserves current behavior
- `CCAControllerStrategy`
  - computes output from forecast-driven slow thermal state logic

The existing coordinator should stop assuming that every cycle is a PI cycle. Instead, it should resolve config, choose the active controller strategy, and ask that strategy for the current `CoordinatorData`.

## Options Flow Design

The options flow should remain the place where users choose the controller mode and configure structural inputs.

### Step layout

#### PI mode path

1. Controller mode
2. Climate entity and operating mode
3. Temperature sensors and target mode
4. Sensor fault and startup mode

#### CCA mode path

1. Controller mode
2. CCA data sources

### Step button labels

The options flow should use wizard-style button labels.

- all steps except the last should show `Next`
- only the final step should show `Submit`

This should match the behavior of the Smart Cover Automation integration.

Implementation note:

- the current integration shows `Submit` on every step
- the CCA work should explicitly include updating the flow behavior so intermediate steps use `Next`

### Step 1: Controller mode

New field:

- `control_mode`

Options:

- `pi`
- `cca`

This is a structural setting. Changing it should trigger a full integration reload.

### CCA Step 2: Data sources

Fields:

- `cca_cooling_enable_entity`
- `cca_weather_entity`
- `cca_forecast_horizon_days`
- `cca_forecast_unavailable_mode`

Meaning:

- `cca_cooling_enable_entity`
  - entity indicating whether cooling is currently active or permitted
- `cca_weather_entity`
  - weather entity used as the source for daily forecasts
- `cca_forecast_horizon_days`
  - number of forecast days considered by the CCA controller
- `cca_forecast_unavailable_mode`
  - fallback behavior when the required forecast data is unavailable

Validation:

- both entities must be configured
- the weather entity must support the required forecast mode

Options:

- `hold`
- `shutdown`
- `zero_output`

Meaning:

- `hold`
  - keep the last auto output until valid forecast data is available again
- `shutdown`
  - treat forecast unavailability as a stop condition
- `zero_output`
  - command 0% output while forecast data is unavailable

## Runtime Settings Via Entities

The following settings should not be part of the options flow. They should be exposed as runtime-configurable entities on the integration instance.

### Manual override

- `cca_manual_override_enabled`
- `cca_manual_output`

### Temperature thresholds

- `cca_hot_day_threshold`
- `cca_warm_night_threshold`

### Output limits

- `cca_output_min`
- `cca_output_max`

### Slow-state tuning

- `cca_charge_gain`
- `cca_discharge_gain`
- `cca_output_step_limit`
- `cca_charge_target_scale`

These should be runtime-configurable and should require only a coordinator refresh, not a full reload.

## Configuration Model

### New structural config keys

- `control_mode`
- `cca_cooling_enable_entity`
- `cca_weather_entity`
- `cca_forecast_horizon_days`
- `cca_forecast_unavailable_mode`
- `cca_update_interval_hours`

### New runtime CCA config keys

- `cca_manual_override_enabled`
- `cca_manual_output`
- `cca_hot_day_threshold`
- `cca_warm_night_threshold`
- `cca_output_min`
- `cca_output_max`
- `cca_charge_gain`
- `cca_discharge_gain`
- `cca_output_step_limit`
- `cca_charge_target_scale`

## Setting Reference

This is the single source of truth for what each CCA setting means. The same wording should later be reused in entity descriptions and UI help text wherever Home Assistant supports it.

### Structural settings

- `control_mode`
  - Selects whether this integration instance runs the existing PI controller or the new CCA controller.
  - Default: `pi`.
- `cca_cooling_enable_entity`
  - Entity that tells the integration whether CCA is allowed to run because cooling is active or enabled.
- `cca_weather_entity`
  - Weather entity used to read the daily forecast for CCA control.
- `cca_forecast_horizon_days`
  - How many forecast days are included when judging whether the building should be pre-cooled.
  - Suggested starting default: `3` days.
- `cca_forecast_unavailable_mode`
  - What the controller should do if the required forecast data cannot be read or understood.
  - Suggested starting default: `hold`.
- `cca_update_interval_hours`
  - How often the CCA controller recalculates its output. This should be much slower than the PI controller.
  - Suggested starting default: `6` hours.

### Runtime settings

- `cca_manual_override_enabled`
  - Turns manual control of the CCA valve on or off.
  - Default: `false`.
- `cca_manual_output`
  - Valve percentage used while manual override is on.
  - Default: `0%`.
- `cca_hot_day_threshold`
  - Outdoor daytime temperature from which a forecast day counts as hot enough to support pre-cooling.
  - Suggested starting default: `26.0 °C`.
- `cca_warm_night_threshold`
  - Outdoor nighttime temperature above which the building is assumed to get too little natural night cooling.
  - Suggested starting default: `18.0 °C`.
- `cca_output_min`
  - Lowest valve percentage the automatic controller may use while it is active.
  - Suggested starting default: `0%`.
- `cca_output_max`
  - Highest valve percentage the automatic controller may use while it is active.
  - Suggested starting default: `60%`.
- `cca_charge_gain`
  - How much cooling the integration should assume is stored during one update interval when the valve output is `100%`.
  - Suggested starting default: `25%` per update when `cca_update_interval_hours = 6`.
- `cca_discharge_gain`
  - How much stored cooling the integration should assume is used during one update interval when the heat load is `100%`.
  - Suggested starting default: `20%` per update when `cca_update_interval_hours = 6`.
- `cca_output_step_limit`
  - Largest change in valve output the automatic controller may make in one update.
  - Suggested starting default: `10%` per update interval.
- `cca_charge_target_scale`
  - How much cooling the integration should aim to store in anticipation of forecast hot weather (below 100%: less, above 100%: more).
  - Suggested starting default: `100%`.

These defaults are intended as conservative starting values for a high-mass supplemental cooling strategy. They should be treated as commissioning defaults, not as universally correct values.

#### Persistence-related defaults

- initial `charge_estimate = 0`
  - used only on first startup when no persisted state is available
- initial `last_auto_output = 0%`
- initial `last_heat_score = 0`
- initial `status = idle`

### Other potentially missing defaults to add

The current plan should also define defaults for the following fields during implementation:

- `current_mode` in CCA mode
  - suggested default state on startup: `off`
- `cca_status`
  - suggested default state on startup: `idle`
- CCA state-restore fallback behavior
  - suggested default: use persisted state when available, otherwise start with zero charge and zero output

### Rationale for the suggested defaults

- A 3-day horizon is sufficient for identifying heat spells without overfitting to low-confidence longer-range forecasts.
- A 26 °C hot-day threshold and 18 °C warm-night threshold are practical initial values for many buildings and align with the general need to detect sustained heat and poor night recovery.
- A `0%` minimum output is the safest initial value because it avoids inventing a baseline cooling demand before field experience shows that a non-zero minimum is useful.
- A 60% automatic output cap reflects the stated goal that CCA is supplemental, not the primary cooling method.
- A 6-hour control cadence fits slow concrete-core behavior much better than minute-scale updates.
- `hold` is the safest initial forecast-failure behavior for a controller whose effect unfolds over many hours.

## CCA Control Algorithm Shape

The initial CCA controller should be forecast-driven and stateful.

The first implementation should use daily forecast highs and lows only. This keeps the controller easier to explain and test, and simple weighting by forecast day index can be added later if the unweighted model proves too coarse.

### Inputs

- cooling enable entity
- daily weather forecast
- runtime thresholds and limits
- persisted internal state from the previous run

### Internal computed values

- forecast heat score
- charge target
- charge estimate
- auto output
- final output

### Percentage-based internal model

The initial CCA controller should use a simple internal stored-cooling model on a `0%` to `100%` scale.

- `charge_estimate = 0%`
  - no stored cooling available
- `charge_estimate = 100%`
  - fully charged according to the controller's internal model

The slow-state tuning settings are meant to work with this percentage-based model.

Suggested interpretation:

$$
charge\_next = clip\left(
charge\_now
+ charge\_gain \cdot \frac{output}{100}
- discharge\_gain \cdot \frac{heat\_load}{100},
0,
100
\right)
$$

Where:

- `output` is the commanded valve percentage from `0` to `100`
- `heat_load` is a normalized forecast heat-load percentage from `0` to `100`
- `charge_gain` is in percentage points per update at `100%` output
- `discharge_gain` is in percentage points per update at `100%` heat load

This means:

- `cca_charge_gain = 25%`
  - if output stays at `100%` for one update interval, the internal stored-cooling estimate increases by `25` percentage points
- `cca_discharge_gain = 20%`
  - if forecast heat load is `100%` for one update interval, the internal stored-cooling estimate decreases by `20` percentage points

The charge target should also use a percentage-based interpretation:

$$
charge\_target = clip\left(heat\_score \cdot \frac{charge\_target\_scale}{100}, 0, 100\right)
$$

So:

- `cca_charge_target_scale = 100%`
  - use the heat score directly as the target, once the heat score has already been normalized to `0` to `100`

### Output

- valve percentage from 0 to 100

### Control sequence

1. Read resolved config.
2. Check whether cooling is active.
3. If cooling is not active, output 0% and mark the controller as inactive.
4. Retrieve weather forecast.
5. Compute a multi-day heat score from forecast highs and lows.
6. Map the heat score to a target charge level.
7. Advance the internal charge estimate using the configured slow-state tuning.
8. Convert charge deficit into an automatic output percentage.
9. Apply output rate limiting.
10. Apply output minimum and maximum limits.
11. If manual override is enabled, replace the automatic output with the manual output.
12. Persist updated internal controller state.

## Persistence Across Restart

CCA mode requires persistence of runtime state, not just configuration values.

### Why persistence is required

The controller models slow thermal storage behavior. If Home Assistant restarts and the controller restarts from an empty state, it loses the estimated thermal charge of the building core and can no longer continue control from a realistic operating point.

### State to persist

- `charge_estimate`
- `last_auto_output`
- `last_heat_score`
- `last_update_iso`
- `status`

### Proposed persistence mechanism

Use a `RestoreEntity`-based CCA state carrier, similar in principle to the existing PI integral-term restoration.

This restore carrier should be treated as an internal persistence mechanism, not as a user-facing UI surface.

### Proposed state model

`CCAState` should contain:

- `charge_estimate: float`
- `last_auto_output: float`
- `last_heat_score: float`
- `last_update_iso: str | None`
- `status: str`

### Proposed restore flow

1. Home Assistant adds the CCA state entity.
2. The entity restores the previously saved state from Home Assistant.
3. The entity passes the restored state into the coordinator.
4. The coordinator restores that state into the CCA controller strategy.
5. The next control cycle resumes from the restored values.

This separates user configuration from runtime control state.

## Entity Design

### Shared entities across modes

- `enabled`
- `output`
- `current_mode`

### PI-only entities

- `proportional_band`
- `integral_time`
- `target_temp`
- `p_term`
- `i_term`
- PI-specific target and deviation entities

### CCA runtime switch

- `cca_manual_override_enabled`

### CCA runtime numbers

- `cca_manual_output`
- `cca_hot_day_threshold`
- `cca_warm_night_threshold`
- `cca_output_min`
- `cca_output_max`
- `cca_charge_gain`
- `cca_discharge_gain`
- `cca_output_step_limit`
- `cca_charge_target_scale`

### CCA diagnostic sensors

- `cca_heat_score`
- `cca_charge_estimate`
- `cca_charge_target`
- `cca_override_active`
- `cca_status`

### Internal restore entity

- `cca_state_store`

This entity should exist only to persist and restore CCA runtime state. It should not be treated as a normal user-facing diagnostic sensor.

### Conditional entity creation

PI-specific entities should only exist in PI mode.

CCA-specific entities should only exist in CCA mode.

The integration already uses conditional entity creation patterns. CCA should follow the same approach.

## Weather Forecast Handling

Forecast interpretation should live behind the Home Assistant interface layer rather than inside the coordinator.

### Proposed helper methods

- `async_validate_daily_forecast_support(entity_id)`
- `async_get_daily_forecasts(entity_id)`
- `_find_forecast_for_date(forecasts, target_date)`
- `_parse_forecast_date(forecast)`
- `_extract_forecast_high(forecast)`
- `_extract_forecast_low(forecast)`

### Expected behavior

- validate weather entity existence
- validate daily forecast support
- request forecast data from Home Assistant's weather integration
- parse both `datetime` and `date` fields
- parse ISO datetimes with trailing `Z`
- ignore malformed forecast entries
- log forecast interpretation problems at debug level where appropriate

## Reload And Refresh Behavior

### Full reload required

- `control_mode`
- `cca_cooling_enable_entity`
- `cca_weather_entity`
- `cca_forecast_horizon_days`
- `cca_forecast_unavailable_mode`

### Coordinator refresh only

- `cca_manual_override_enabled`
- `cca_manual_output`
- `cca_hot_day_threshold`
- `cca_warm_night_threshold`
- `cca_output_min`
- `cca_output_max`
- `cca_charge_gain`
- `cca_discharge_gain`
- `cca_output_step_limit`
- `cca_charge_target_scale`

## File-Level Implementation Plan

### `custom_components/pi_thermostat/const.py`

Add:

- `ControlMode`
- `CCAForecastUnavailableMode`
- CCA entity key constants
- CCA default constants

### `custom_components/pi_thermostat/config.py`

Add:

- new `ConfKeys`
- new `ResolvedConfig` fields
- default values and converters for all new CCA fields
- runtime-configurable markers for entity-managed CCA tuning

### `custom_components/pi_thermostat/config_flow.py`

Add:

- new first step for controller mode
- PI steps shifted from 3-step to 4-step flow
- CCA-specific step 2
- CCA validation for weather entity support

### `custom_components/pi_thermostat/ha_interface.py`

Add:

- forecast capability validation
- daily forecast retrieval
- forecast entry parsing helpers
- high and low temperature extraction helpers

### `custom_components/pi_thermostat/coordinator.py`

Refactor:

- stop assuming every cycle is PI
- branch by `control_mode`
- delegate to PI or CCA strategy
- add `restore_cca_state(...)`

### `custom_components/pi_thermostat/cca_controller.py`

Create:

- `CCAControllerStrategy`
- `CCAState`
- forecast score, charge estimate, rate limiting, and output selection logic

### `custom_components/pi_thermostat/number.py`

Add conditional CCA numbers.

### `custom_components/pi_thermostat/switch.py`

Add conditional CCA manual override switch.

### `custom_components/pi_thermostat/sensor.py`

Add conditional CCA diagnostic sensors and the `RestoreEntity`-based state carrier.

### `custom_components/pi_thermostat/__init__.py`

Update reload behavior to distinguish structural CCA changes from runtime tuning changes.

### `custom_components/pi_thermostat/translations/en.json`

Add:

- controller mode labels
- updated 4-step wizard labels
- CCA field descriptions
- CCA entity names

## Testing Plan

### Config flow tests

- new controller-mode step appears first
- PI path still works after being shifted to steps 2 to 4
- CCA path validates weather entity support
- CCA path rejects incomplete or invalid source wiring

### Forecast parsing tests

- accepts forecast entries with `datetime`
- accepts forecast entries with `date`
- accepts ISO timestamps with `Z`
- ignores malformed dates
- handles empty or missing forecast results

### CCA controller tests

- output is 0 when cooling is disabled
- manual override replaces auto output
- output is clamped by limits
- output changes are rate-limited
- heat score maps to charge target correctly
- restart restore resumes from prior charge estimate

### Entity tests

- CCA entities only exist in CCA mode
- PI-only entities do not appear in CCA mode
- persisted CCA state is restored correctly

## Phased Implementation Order

### Phase 1

- add `control_mode`
- add options flow step 1
- shift PI flow to 4 steps
- add CCA config skeleton only

### Phase 2

- add CCA runtime entities
- add forecast helpers
- add conditional entity creation by mode

### Phase 3

- add CCA controller strategy
- add persistence of CCA runtime state
- add restart restore path

### Phase 4

- add tests
- refine translations
- tune defaults

## Recommendation

Proceed with implementation in phases, starting with the mode-selection infrastructure and the CCA configuration skeleton.

That yields the least risky first change, preserves backward compatibility, and keeps review of the control algorithm separate from the initial wiring work.