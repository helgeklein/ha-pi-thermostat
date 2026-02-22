# PI Thermostat — Implementation Plan

This document describes how to transform the **Smart Cover Automation** template into a **PI Thermostat** integration for Home Assistant. The integration uses a PI (proportional–integral) control algorithm to calculate a heating/cooling output percentage based on the difference between a target temperature and a measured current temperature.

**Library**: [simple-pid](https://pypi.org/project/simple-pid/) (set Kd=0 for PI-only control).

---

## Progress

| Step | Phase | Description | Status |
|---|---|---|---|
| 1 | 1 | Template cleanup: delete files, rename, string replacements, update metadata, clean `__init__.py` (§1) | **DONE** |
| 2 | 2 | Strip `const.py`, define new constants (§2.1) | **DONE** |
| 3 | 2 | Strip `config.py`, define ConfKeys + CONF_SPECS + ResolvedConfig (§2.2) | **DONE** |
| 4 | 2 | Strip `data.py`, define CoordinatorData + RuntimeData (§2.3) | **DONE** |
| 5 | 3 | Create `pi_controller.py` with PIController + PIResult (§3.1) | **DONE** |
| 6 | 3 | Write unit tests for `pi_controller.py` (§7.2) | **DONE** |
| 7 | 3 | Strip `ha_interface.py`, implement new methods (§3.3) | **DONE** |
| 8 | 3 | Strip `coordinator.py`, implement new update loop (§3.2) | **DONE** |
| 9 | 4 | Verify `entity.py` base class (§4.1) | **DONE** |
| 10 | 4 | Implement `sensor.py` with RestoreEntity for i_term (§4.2, §3.4) | **DONE** |
| 11 | 4 | Implement `number.py` (§4.3) | **DONE** |
| 12 | 4 | Implement `switch.py` (§4.4) | **DONE** |
| 13 | 4 | Implement `binary_sensor.py` (§4.5) | **DONE** |
| 14 | 5 | Implement config flow + options flow (§5) | **DONE** |
| 15 | 6 | Create `translations/en.json` (§6) | **DONE** |
| 16 | 7 | Write remaining tests (§7) | **DONE** |
| 17 | 7 | Lint + type-check + full test run | **DONE** |
| 18 | 8 | Update docs/README (§8) | Not started |

**Next step**: 18 — Update docs/README (Phase 8).

**Notes**:
- Phase 1 validated: lint passes. README.md body content still has cover-specific text — full rewrite deferred to Phase 8.
- Phase 2 validated: lint passes. `const.py`, `config.py`, `data.py` rewritten with PI thermostat types.
- Phase 3 validated: lint passes, 40 unit tests pass. `pi_controller.py` (new), `ha_interface.py`, `coordinator.py` rewritten.
- Phase 4 validated: lint passes, 40 unit tests pass. `entity.py` unchanged (already correct). `sensor.py`, `number.py`, `switch.py`, `binary_sensor.py` rewritten with PI thermostat entities.
- Phase 5-6 validated: lint passes, Pyright clean. `config_flow.py` rewritten (minimal config flow + 3-step options wizard). `translations/en.json` rewritten with all entity names, config/options flow labels, selector translations, error messages.
- Phase 7 validated: lint passes, Pyright clean, **263 tests pass, 97% overall coverage**. Test files:
  - `test_pi_controller.py` — 40 tests: PI logic, clamping, mode switching, HVAC unit conversion, anti-windup.
  - `test_const.py` — 29 tests (previously 24): constants, enums, entity keys.
  - `test_config.py` — 32 tests: ConfKeys, CONF_SPECS, resolve(), ResolvedConfig.
  - `test_config_flow.py` — 30 tests: config flow + 3-step options wizard, validation, schema builders.
  - `test_coordinator.py` — 34 tests: PI control cycle, pause, auto-disable, sensor faults.
  - `test_entities.py` — 20 tests: full integration setup, entity platforms, I-term startup modes (zero, fixed, last + restore), switch write (turn on/off), number write (set value).
  - `test_ha_interface.py` — 38 tests: state reading, service calls, error handling.
  - `test_init.py` — 11 tests: setup/unload error handling, options flow handler, smart reload logic (runtime vs structural vs mixed changes).
  - `test_util.py` — 29 tests: to_float_or_none, to_int_or_none coercion helpers.
  - Per-module coverage: `__init__.py` 100%, `binary_sensor.py` 100%, `config.py` 98%, `config_flow.py` 100%, `coordinator.py` 97%, `data.py` 100%, `entity.py` 100%, `ha_interface.py` 100%, `number.py` 100%, `switch.py` 100%, `util.py` 100%, `pi_controller.py` 99%, `sensor.py` 96%, `log.py` 90%, `const.py` 84%.

---

## Phase 1: Template Cleanup — Rename, Delete, Adjust

### 1.1 Delete Domain-Specific Files

Remove files that contain cover-automation-specific logic with no counterpart in the PI thermostat:

| File | Reason |
|---|---|
| `automation_engine.py` | Cover-specific logic; replaced by `pi_controller.py` |
| `cover_automation.py` | Cover-specific per-cover state machine |
| `cover_position_history.py` | Cover position tracking, not needed |
| `select.py` | Lock mode select entity; not needed initially |
| `services.yaml` | Cover-specific services (set_lock, logbook_entry); new services TBD |

### 1.2 Rename the Integration Folder

```
custom_components/smart_cover_automation/  →  custom_components/pi_thermostat/
```

### 1.3 Global String Replacements

Perform project-wide replacements (source files, tests, config, pyproject.toml, etc.):

| Old | New |
|---|---|
| `smart_cover_automation` | `pi_thermostat` |
| `Smart Cover Automation` | `PI Thermostat` |
| `SmartCover` (in class names) | `PiThermostat` |

### 1.4 Update `manifest.json`

```json
{
    "domain": "pi_thermostat",
    "name": "PI Thermostat",
    "codeowners": ["@helgeklein"],
    "config_flow": true,
    "dependencies": [],
    "documentation": "https://github.com/helgeklein/ha-pi-thermostat",
    "iot_class": "calculated",
    "issue_tracker": "https://github.com/helgeklein/ha-pi-thermostat/issues",
    "requirements": ["simple-pid==2.0.1"],
    "version": "0.1.0"
}
```

Key changes:
- No dependencies on `sun`, `weather`, `logbook`.
- Add `simple-pid` to `requirements`.
- Reset version to `0.1.0`.

### 1.5 Update `hacs.json`

```json
{
    "name": "PI Thermostat",
    "render_readme": true
}
```

### 1.6 Update `pyproject.toml`

- Change coverage source to `custom_components/pi_thermostat`.
- Update project metadata (name, description).

### 1.7 Update `config/configuration.yaml`

- Replace logger domain with `custom_components.pi_thermostat`.

### 1.8 Update `requirements.txt`

- Add `simple-pid==2.0.1`.

### 1.9 Delete All Existing Tests

Delete all files under `tests/` except `__init__.py`. Tests will be written from scratch to match the new integration logic.

### 1.10 Clean Up `__init__.py`

- Remove imports of cover-specific modules (`automation_engine`, `cover_automation`).
- Remove cover-specific services (set_lock, logbook_entry).
- Remove unique ID migration logic (fresh integration, no legacy IDs).
- Keep: setup/unload/reload lifecycle, smart reload pattern, platform forwarding, coordinator creation.
- Update `PLATFORMS` list (see Phase 3).

---

## Phase 2: Define Constants, Configuration, and Data Types

### 2.1 `const.py` — New Constants

**Remove all** cover-specific constants (azimuths, positions, weather conditions, lock modes, cover entity keys, etc.).

**Define new constants**:

```python
DOMAIN = "pi_thermostat"
INTEGRATION_NAME = "PI Thermostat"

# Coordinator
UPDATE_INTERVAL_DEFAULT_SECONDS = 60       # Default update interval

# PI controller defaults (HVAC-standard units)
DEFAULT_PROP_BAND = 4.0                    # Proportional band in Kelvin
DEFAULT_INT_TIME = 120.0                   # Integral time (reset time) in minutes
DEFAULT_OUTPUT_MIN = 0.0                   # Minimum output %
DEFAULT_OUTPUT_MAX = 100.0                 # Maximum output %
DEFAULT_SAMPLE_TIME_SECONDS = 60           # Must match update interval

# Entity keys — sensors (read-only, from coordinator data)
SENSOR_KEY_OUTPUT = "output"               # PI output percentage
SENSOR_KEY_ERROR = "error"                 # Current error (target - actual)
SENSOR_KEY_P_TERM = "p_term"              # Proportional component
SENSOR_KEY_I_TERM = "i_term"              # Integral component (also persisted)

# Entity keys — number entities (writable, runtime-configurable)
NUMBER_KEY_PROP_BAND = "proportional_band" # Proportional band (K)
NUMBER_KEY_INT_TIME = "integral_time"      # Integral time (min)
NUMBER_KEY_UPDATE_INTERVAL = "update_interval"

# Entity keys — switches
SWITCH_KEY_ENABLED = "enabled"             # Enable/disable the controller

# Entity keys — binary sensors
BINARY_SENSOR_KEY_ACTIVE = "active"        # Whether output > 0

# Operating mode
class OperatingMode(StrEnum):
    HEAT_COOL = "heat_cool"           # Auto: read mode from a climate entity
    HEAT = "heat"                     # Heating only
    COOL = "cool"                     # Cooling only

# Sensor fault behavior
class SensorFaultMode(StrEnum):
    SHUTDOWN = "shutdown"                  # Set output to 0%
    HOLD = "hold"                          # Hold last output for grace period, then shutdown

# Safety
SENSOR_FAULT_GRACE_PERIOD_SECONDS = 300    # 5 minutes before shutdown when in HOLD mode
```

### 2.2 `config.py` — Settings Registry

**`ConfKeys` enum** — new settings:

| Key | Type | Default | Runtime-Configurable | Description |
|---|---|---|---|---|
| `ENABLED` | bool | True | Yes | Master on/off |
| `CLIMATE_ENTITY` | str | "" | No | Climate entity for multi-purpose use (see below). Optional but central. |
| `TEMP_SENSOR` | str | "" | No | Entity ID of the current temperature sensor. If empty and a climate entity is configured, `current_temperature` from the climate entity is used. |
| `TARGET_TEMP_MODE` | str | "internal" | No | "internal" (built-in setpoint), "external" (explicit entity), or "climate" (from climate entity's setpoint) |
| `TARGET_TEMP_ENTITY` | str | "" | No | Entity ID for external target temp (only when target_temp_mode=external) |
| `TARGET_TEMP` | float | 20.0 | Yes | Built-in target temperature setpoint (only when target_temp_mode=internal) |
| `OPERATING_MODE` | str | "heat_cool" | No | "heat_cool" (auto from climate entity), "heat", or "cool" |
| `AUTO_DISABLE_ON_HVAC_OFF` | bool | True | Yes | When True, controller output is 0% if the climate entity's `hvac_mode` is "off". Only applies when a climate entity is configured. |
| `PROPORTIONAL_BAND` | float | 4.0 | Yes | Proportional band in Kelvin (K). The temperature range over which output goes from 0% to 100%. Smaller = more aggressive. |
| `INTEGRAL_TIME` | float | 120.0 | Yes | Integral time (reset time) in minutes. The time for the integral action to repeat the proportional action. Larger = slower integral response. |
| `OUTPUT_ENTITY` | str | "" | No | Entity to receive the output value (optional) |
| `OUTPUT_MIN` | float | 0.0 | Yes | Minimum output limit |
| `OUTPUT_MAX` | float | 100.0 | Yes | Maximum output limit |
| `UPDATE_INTERVAL` | int | 60 | Yes | Update interval in seconds |
| `SENSOR_FAULT_MODE` | str | "shutdown" | No | Behavior when temp sensor unavailable |

**Climate entity as multi-purpose source**: When a climate entity is configured, it can serve as the source for up to four pieces of information, reducing the number of entities the user needs to specify:

| Purpose | Climate Attribute Used | Fallback / Alternative |
|---|---|---|
| Heat/cool direction | `hvac_action` (heating/cooling/idle) | Fixed via operating_mode (heat/cool) |
| Current temperature | `current_temperature` | Dedicated temperature sensor entity |
| Target temperature | `temperature` (setpoint) | Internal setpoint or dedicated entity |
| Auto-disable | `hvac_mode` (off → output 0%) | Manual enabled switch |

**`ResolvedConfig`** — frozen dataclass with typed fields matching the above.

### 2.3 `data.py` — Runtime Data Types

```python
@dataclass
class CoordinatorData:
    """Output of each coordinator update cycle."""

    output: float               # PI output percentage (0–100)
    error: float | None         # target - current (or current - target in cool mode)
    p_term: float | None        # Proportional component
    i_term: float | None        # Integral component
    current_temp: float | None  # Current temperature reading
    target_temp: float | None   # Active target temperature
    sensor_available: bool      # Whether the temperature sensor is available
    controller_active: bool     # Whether the controller is actively outputting > 0

@dataclass
class RuntimeData:
    """Stored on config_entry.runtime_data."""

    coordinator: DataUpdateCoordinator
    integration: Integration
    config: dict[str, Any]
```

---

## Phase 3: Implement Core Logic

### 3.1 `pi_controller.py` — Business Logic (New File)

Pure Python module with **no Home Assistant imports**. Wraps `simple-pid`:

```python
class PIController:
    """PI controller wrapping simple-pid for HVAC temperature control.

    Uses HVAC-standard parameterization:
    - Proportional Band (K): temperature range over which output spans 0–100%.
      Converted to simple-pid Kp: Kp = 100 / proportional_band
    - Integral Time (min): time for integral action to repeat proportional action.
      Converted to simple-pid Ki: Ki = Kp / (integral_time_minutes * 60)
    """

    @staticmethod
    def hvac_to_pid_gains(proportional_band: float, integral_time_min: float) -> tuple[float, float]:
        """Convert HVAC-standard parameters to simple-pid Kp/Ki.

        Args:
            proportional_band: Proportional band in Kelvin.
            integral_time_min: Integral time (reset time) in minutes.

        Returns:
            Tuple of (Kp, Ki) for simple-pid.
        """
        kp = 100.0 / proportional_band
        ki = kp / (integral_time_min * 60.0)
        return kp, ki

    def __init__(self, proportional_band, integral_time_min, output_min, output_max,
                 sample_time, is_cooling: bool = False):
        kp, ki = self.hvac_to_pid_gains(proportional_band, integral_time_min)
        self._pid = PID(Kp=kp, Ki=ki, Kd=0,
                        setpoint=target_temp,
                        sample_time=sample_time,
                        output_limits=(output_min, output_max))
        self._is_cooling = is_cooling
        self._apply_sign()

    def _apply_sign(self) -> None:
        """Apply sign to gains based on current mode (heating=positive, cooling=negative)."""
        if self._is_cooling:
            self._pid.Kp = -abs(self._pid.Kp)
            self._pid.Ki = -abs(self._pid.Ki)
        else:
            self._pid.Kp = abs(self._pid.Kp)
            self._pid.Ki = abs(self._pid.Ki)

    def set_cooling(self, is_cooling: bool) -> None:
        """Switch between heating and cooling mode at runtime (for heat_cool operating mode)."""
        if is_cooling != self._is_cooling:
            self._is_cooling = is_cooling
            self._apply_sign()

    def update(self, current_temp: float) -> PIResult:
        """Run one PI iteration. Returns PIResult with output and components."""

    def set_target(self, target: float) -> None:
        """Update the setpoint."""

    def update_tunings(self, proportional_band: float, integral_time_min: float) -> None:
        """Update gains at runtime. Accepts HVAC-standard units, converts internally."""

    def get_integral_term(self) -> float:
        """Return current integral term for persistence."""

    def restore_integral_term(self, value: float) -> None:
        """Restore integral term after restart."""

    def reset(self) -> None:
        """Reset the controller (clear integral term)."""

@dataclass(frozen=True)
class PIResult:
    """Result of a single PI computation."""
    output: float
    error: float
    p_term: float
    i_term: float
```

**Key design decisions**:
- **HVAC-standard units**: Users configure Proportional Band (K) and Integral Time (min) — the familiar parameterization for heating/cooling controllers. The conversion to `simple-pid`'s Kp/Ki happens internally in `PIController`.
  - `Kp = 100 / proportional_band` — e.g., a 4 K band → Kp = 25 (100% output change per 4°C error).
  - `Ki = Kp / (integral_time × 60)` — e.g., 30 min reset time with Kp=25 → Ki ≈ 0.0139.
- `Kd` is always 0 — never exposed.
- Cooling mode is handled by negating gains, not the error. This keeps `simple-pid`'s anti-windup working correctly.
- The controller accepts an `is_cooling` flag rather than the full operating mode. The coordinator is responsible for resolving the operating mode (heat_cool → read climate entity; heat/cool → static) into this boolean.
- `set_cooling()` allows runtime mode switching for heat_cool mode without re-creating the controller.
- `PIResult` is a simple value object — no HA types.

### 3.2 `coordinator.py` — Update Loop

```
_async_update_data():
    1. Resolve config (latest options + defaults).
    2. Check auto-disable: if climate entity configured and auto_disable_on_hvac_off=True,
       read hvac_mode from climate entity. If "off" → return CoordinatorData with output=0.
    3. Determine effective heating/cooling direction:
       - heat_cool mode: read hvac_action from climate entity (via ha_interface).
         Call pi_controller.set_cooling(is_cooling).
       - heat mode: always heating (is_cooling=False).
       - cool mode: always cooling (is_cooling=True).
    4. Read current temperature:
       - If temp_sensor configured → read from that sensor.
       - Else if climate entity configured → read current_temperature attribute.
       - Else → sensor fault.
    5. Determine target temperature:
       - Internal mode: from resolved config (number entity persists to options).
       - External mode: read from dedicated entity (via ha_interface).
       - Climate mode: read setpoint (temperature attribute) from climate entity.
    6. Handle sensor faults:
       - If current_temp unavailable → apply fault mode (shutdown or hold+grace period).
    7. Update PI controller tunings if Proportional Band/Integral Time/limits changed.
    8. Run pi_controller.update(current_temp) → PIResult.
    9. Optionally write output to the configured output entity (via ha_interface).
    10. Return CoordinatorData.
```

### 3.3 `ha_interface.py` — HA API Abstraction

Replace all cover/weather methods with:

| Method | Purpose |
|---|---|
| `get_temperature(entity_id)` | Read current temp from a sensor entity. Return float or None if unavailable. |
| `get_climate_current_temperature(entity_id)` | Read `current_temperature` attribute from a climate entity. Return float or None. |
| `get_target_temperature(entity_id)` | Read target temp from an external entity (number, input_number, climate). |
| `get_climate_target_temperature(entity_id)` | Read `temperature` (setpoint) attribute from a climate entity. Return float or None. |
| `get_climate_hvac_action(entity_id)` | Read the `hvac_action` attribute from a climate entity. Returns "heating" or "cooling" (or None if idle/unavailable). Used in heat_cool mode. |
| `get_climate_hvac_mode(entity_id)` | Read the `hvac_mode` (state) from a climate entity. Returns "off", "heat", "cool", etc. Used for auto-disable. |
| `set_output(entity_id, value)` | Write the PI output to an entity (input_number, number, or climate). |
| `is_entity_available(entity_id)` | Check entity state != unavailable/unknown. |

### 3.4 Integral Term Persistence

The integral term must survive HA restarts. Strategy: **use `RestoreEntity`** on the I-term sensor.

```
Startup:
    1. I-term sensor is created with RestoreEntity mixin.
    2. In async_added_to_hass(), restore the last known i_term value.
    3. Pass it to the coordinator → pi_controller.restore_integral_term(value).

Runtime:
    4. Each coordinator cycle updates the sensor with the current i_term.
    5. HA's RestoreEntity infrastructure automatically persists it.

Restart:
    6. Steps 1–3 run again, restoring the integral from the sensor's last state.
```

This is cleaner than writing to config_entry options (which would trigger reload listeners).

---

## Phase 4: Implement Entities

### 4.1 Platforms to Register

```python
PLATFORMS = [Platform.BINARY_SENSOR, Platform.NUMBER, Platform.SENSOR, Platform.SWITCH]
```

No `select` platform needed initially.

### 4.2 Sensors (Read-Only)

| Key | Name | Unit | Device Class | Description |
|---|---|---|---|---|
| `output` | Output | `%` | `power_factor` | PI output percentage |
| `error` | Error | `°C` | `temperature` | target − current |
| `p_term` | P Term | — | — | Proportional component |
| `i_term` | I Term | — | — | Integral component (RestoreEntity) |

The `i_term` sensor uses the `RestoreEntity` mixin for integral persistence across restarts.

### 4.3 Number Entities (Writable, Runtime-Configurable)

| Key | Name | Min | Max | Step | Unit | Description |
|---|---|---|---|---|---|---|
| `proportional_band` | Proportional Band | 0.5 | 30 | 0.1 | K | Temperature range (in Kelvin) over which the output spans 0–100%. Smaller = more aggressive. |
| `integral_time` | Integral Time | 1 | 600 | 1 | min | Time (in minutes) for the integral action to repeat the proportional action. Larger = slower integral response. |
| `target_temp` | Target Temperature | 5 | 35 | 0.1 | °C | Setpoint (only when target_temp_mode=internal) |
| `output_min` | Output Min | 0 | 100 | 1 | % | Minimum output limit |
| `output_max` | Output Max | 0 | 100 | 1 | % | Maximum output limit |
| `update_interval` | Update Interval | 10 | 600 | 10 | s | Coordinator update interval |

All writable entities use `_async_persist_option()` → triggers smart reload (runtime-configurable keys refresh coordinator without full reload).

### 4.4 Switches (Writable)

| Key | Name | Description |
|---|---|---|
| `enabled` | Enabled | Master on/off. When off, there is no output and PI controller is paused. |

### 4.5 Binary Sensors (Read-Only)

| Key | Name | Description |
|---|---|---|
| `active` | Active | On when output > 0 (useful for automations/dashboard) |

---

## Phase 5: Config Flow & Options Flow

### 5.1 Config Flow (Initial Setup)

The config flow has **no user-configurable fields**. It creates the config entry with all defaults from `CONF_SPECS` and prompts HA for the instance name (standard HA behavior via the title input).

This follows the HA pattern where the config flow is a minimal "add integration" action, and all real configuration happens in the options flow.

### 5.2 Options Flow (Post-Setup Configuration)

**Step 1 — Climate Entity & Operating Mode**:

| Field | Description |
|---|---|
| Climate entity | Entity selector (domain: climate) — optional but central. When configured, can serve as source for current temp, target temp, heat/cool direction, and auto-disable. |
| Operating mode | Select: "Heat + Cool" (default), "Heat only", "Cool only". "Heat + Cool" requires a climate entity (reads `hvac_action`). |
| Auto-disable on HVAC off | Switch (default: on). When enabled and a climate entity is configured, output is 0% whenever the climate entity's `hvac_mode` is "off". |

**Step 2 — Temperature Sensors & Target**:

| Field | Description |
|---|---|
| Temperature sensor | Entity selector (domain: sensor, device_class: temperature) — optional if a climate entity is configured (falls back to `current_temperature` from the climate entity). Shown with hint: "Leave empty to use the climate entity's current temperature". |
| Target temperature mode | "Internal" (built-in setpoint), "External" (explicit entity), or "Climate" (from climate entity's setpoint — only shown when a climate entity is configured) |
| Target temperature entity | Entity selector (only shown when mode=external) |
| Target temperature | Number (only shown when mode=internal, also adjustable via number entity) |

**Step 3 — PI Tuning**:

| Field | Description |
|---|---|
| Proportional Band | Temperature range in Kelvin over which output spans 0–100% (smaller = more aggressive) |
| Integral Time | Reset time in minutes for the integral action to repeat the proportional action (larger = slower) |
| Output min | Minimum output % |
| Output max | Maximum output % |

**Step 4 — Output & Timing**:

| Field | Description |
|---|---|
| Output entity | Entity to write output to (optional; input_number or number entity) |
| Update interval | Seconds between calculations |
| Sensor fault mode | Shutdown immediately or hold + grace period |

### 5.3 Validation

- At least one temperature source must be configured: either a temperature sensor entity or a climate entity (to read `current_temperature` from).
- Temperature sensor, if specified, must exist and have device_class=temperature.
- Climate entity, if specified, must exist and be a climate entity.
- Operating mode "heat_cool" requires a climate entity (to read `hvac_action`).
- Target temp mode "climate" requires a climate entity.
- Target temp entity must exist (if target_temp_mode=external).
- Output entity must be writable (if specified).
- Proportional Band must be > 0 (division by zero otherwise).
- Integral Time must be > 0 (division by zero otherwise).
- Output min must be < output max.

---

## Phase 6: Translations

### 6.1 `translations/en.json`

Structure mirrors the template:
- `config.step` — Setup wizard labels/descriptions.
- `options.step` — Options flow labels/descriptions.
- `options.error` — Validation error messages.
- `entity.*` — Names for all sensor, number, switch, binary_sensor entities.

### 6.2 Initial Language

Start with English only. Add more languages later.

---

## Phase 7: Testing

### 7.1 Test Structure

```
tests/
├── conftest.py                  # Fixtures: mock_hass, coordinator, PI controller instances
├── unit/
│   ├── test_pi_controller.py    # Pure PI logic: output values, clamping, mode, reset, HVAC unit conversion
│   ├── test_config.py           # ConfKeys, CONF_SPECS, resolve()
│   ├── test_const.py            # Constants, enums
│   └── test_data.py             # Dataclass construction
├── components/
│   ├── test_sensor.py           # Output, error, p_term, i_term sensors
│   ├── test_number.py           # Kp, Ki, target_temp number entities
│   ├── test_switch.py           # Enabled switch
│   └── test_binary_sensor.py    # Active binary sensor
├── coordinator/
│   ├── test_update_cycle.py     # Normal operation: reads temp, computes, returns data
│   ├── test_sensor_fault.py     # Unavailable sensor handling (shutdown, hold, grace)
│   ├── test_tuning_changes.py   # Runtime Proportional Band/Integral Time/limits changes
│   ├── test_setpoint_changes.py # Target temp changes (internal + external)
│   └── test_mode.py             # Heat vs cool vs heat_cool mode
├── config_flow/
│   ├── test_config_flow.py      # Initial setup flow (100% coverage)
│   └── test_options_flow.py     # Options flow (100% coverage)
├── ha_interface/
│   └── test_ha_interface.py     # get_temperature, set_output, etc.
├── initialization/
│   ├── test_setup.py            # async_setup_entry lifecycle
│   ├── test_unload.py           # async_unload_entry cleanup
│   └── test_reload.py           # Smart reload (runtime vs full)
├── integration/
│   ├── test_heating_scenario.py # End-to-end: cold room → steady state
│   ├── test_cooling_scenario.py # End-to-end: cooling mode
│   └── test_restart_restore.py  # Integral persistence across restarts
├── edge_cases/
│   ├── test_boundary_values.py  # Min/max temps, zero gains, etc.
│   └── test_invalid_config.py   # Bad entity IDs, missing sensors
└── localization/
    └── test_translations.py     # Translation completeness
```

### 7.2 Key Test Scenarios for PI Logic

| Scenario | What to Verify |
|---|---|
| Steady state | Output stabilizes when current ≈ target |
| Cold start | Output ramps up from 0 when current << target |
| Overshoot | Output decreases when current > target (integral wind-down) |
| Output clamping | Output stays within [output_min, output_max] |
| Anti-windup | Integral term doesn't grow when output is saturated |
| Cooling mode | Positive output when current > target |
| Heat+cool mode | Controller reads climate entity hvac_action, switches sign dynamically |
| Mode switching | Integral term behaves correctly across heat↔cool transitions |
| Climate auto-disable | Output is 0 when climate entity hvac_mode is "off" |
| Climate as temp source | current_temperature read from climate entity when no dedicated sensor |
| Climate as target source | setpoint read from climate entity when target_temp_mode=climate |
| Tuning change | Output responds correctly after Proportional Band / Integral Time change at runtime |
| Setpoint jump | Controller adapts to large setpoint change |
| Integral restore | After simulated restart, output resumes at prior level |
| Sensor unavailable | Output goes to 0 (shutdown mode) or holds (hold mode) |
| Controller disabled | Output is 0 when enabled=false |

### 7.3 Fixtures (`conftest.py`)

```python
# Mock entities
MOCK_TEMP_SENSOR = "sensor.living_room_temperature"
MOCK_TARGET_ENTITY = "input_number.target_temp"
MOCK_OUTPUT_ENTITY = "input_number.heating_output"

# Test values
TEST_CURRENT_TEMP = 18.5
TEST_TARGET_TEMP = 21.0
TEST_PROP_BAND = 4.0       # Proportional band in Kelvin
TEST_INT_TIME = 30.0       # Integral time in minutes

# Config builder
def create_pi_config(**overrides) -> dict[str, Any]: ...

# Coordinator fixture
@pytest.fixture
def coordinator(mock_hass) -> DataUpdateCoordinator: ...

# Pure PI controller fixture (no HA)
@pytest.fixture
def pi_controller() -> PIController: ...
```

---

## Phase 8: Documentation & Metadata

- Update `README.md` with PI thermostat description, installation, configuration.
- Update `CONTRIBUTING.md` as needed.
- Delete `developer_docs/integration-template-guide.md`.
- Don't update `docs/` site content (will be done manually).

---

## Architecture Diagram

```
┌───────────────────────────────────────────────────────────┐
│                     Home Assistant                         │
│                                                            │
│  ┌──────────────┐    ┌──────────────────────────────┐      │
│  │ Config Flow   │───▶│ config_entry.options          │     │
│  │ Options Flow  │    │  - temp_sensor entity ID      │     │
│  └──────────────┘    │  - target_temp / mode          │     │
│                       │  - prop_band (K), int_time (min)│    │
│                       │  - output limits, entity, interval│  │
│                       └──────────┬────────────────────┘     │
│                                  │                          │
│  ┌───────────────────────────────▼───────────────────┐     │
│  │              __init__.py                           │     │
│  │   async_setup_entry / unload / smart reload        │     │
│  └───────────────────┬───────────────────────────────┘     │
│                       │                                     │
│  ┌────────────────────▼──────────────────────────────┐     │
│  │          DataUpdateCoordinator                     │     │
│  │   - Reads current temp & target (via ha_interface) │     │
│  │   - Detects sensor faults                          │     │
│  │   - Delegates to PIController                      │     │
│  │   - Writes output to entity (via ha_interface)     │     │
│  │   - Returns CoordinatorData                        │     │
│  └────┬──────────────────────────────┬───────────────┘     │
│       │                              │                      │
│  ┌────▼──────────┐     ┌────────────▼────────────────┐    │
│  │ HA Interface   │     │      PIController           │    │
│  │ (ha_interface) │     │   (pi_controller.py)        │    │
│  │                │     │                             │    │
│  │ get_temperature│     │   - Wraps simple-pid        │    │
│  │ get_target_temp│     │   - PI only (Kd=0)          │    │
│  │ set_output     │     │   - Heat/Cool modes         │    │
│  │ is_available   │     │   - Anti-windup via limits   │    │
│  └───────────────┘     │   - No HA imports            │    │
│                         └─────────────────────────────┘    │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │                 Entity Layer                         │   │
│  │  IntegrationEntity (base)                           │   │
│  │    ├── Sensors: output, error, p_term, i_term       │   │
│  │    │   (i_term uses RestoreEntity for persistence)  │   │
│  │    ├── Numbers: prop_band, int_time, target, limits  │  │
│  │    ├── Switch: enabled                              │   │
│  │    └── Binary Sensor: active                        │   │
│  │                                                     │   │
│  │  Read-only entities  ← CoordinatorData              │   │
│  │  Writable entities   → config_entry.options         │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```
