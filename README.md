# PI Thermostat & CCA Control for Home Assistant

[![Test status](https://github.com/helgeklein/ha-pi-thermostat-cca-control/actions/workflows/test.yml/badge.svg)](https://github.com/helgeklein/ha-pi-thermostat-cca-control/actions/workflows/test.yml)
[![Test coverage](https://raw.githubusercontent.com/helgeklein/ha-pi-thermostat-cca-control/main/.github/badges/coverage.svg)](https://github.com/helgeklein/ha-pi-thermostat-cca-control/actions/workflows/test.yml)

A Home Assistant integration to control your smart home's thermal actuators, optimized for radiant ceiling heating & cooling as well as for cooling via concrete core activation (CCA). The integration provides two controller modes: **PI (proportional-integral)** and **CCA (concrete core activation)**. It calculates a heating or cooling output percentage and exposes the result as a sensor for use in automations.

## Features

### PI Controller for Radiant Ceilint Heating & Cooling

- **PI control algorithm:**
   - Industry-standard proportional–integral controller (PID with Kd=0).
   - Powered by the [simple-pid](https://pypi.org/project/simple-pid/) library.
   - Tunable proportional band (K) and integral time (minutes) - adjustable at runtime.
   - Anti-windup protection and output clamping (configurable min/max %).
- **Flexible temperature sources:**
   - Read the current temperature from a **temperature sensor** or a **climate entity**.
   - Target temperature via **built-in setpoint**, **external entity**, or **climate entity**.
- **Operating modes:**
   - **Heating only**, **cooling only**, or **auto (heat + cool)**.
   - In auto mode, the heating/cooling direction is read from a climate entity's HVAC action.
   - Optional auto-disable when the climate entity's HVAC mode is "off".
- **Output control:**
   - Use the output value in automations to control valves, heaters, fans, etc.
- **Sensor fault handling:**
   - **Shutdown immediately:** Set output to 0 % when the temperature sensor becomes unavailable.
   - **Hold last output:** Maintain the last output for a 30-minute grace period, then shut down.
- **I-term persistence across restarts and upgrades:**
   - The integral term is saved via Home Assistant's `RestoreEntity` mechanism.
   - Configurable startup modes: **last persisted**, **fixed value**, or **zero**.
- **Runtime-configurable entities:**
   - Number entities for proportional band, integral time, target temperature, output min/max, and update interval - all adjustable without reconfiguring.
   - `Enabled` switch to pause/resume the controller.
- **Diagnostic sensors:**
   - Output %, deviation, proportional term, integral term.

### CCA Controller for Cooling via Concrete Core Activation

- **Forecast-driven cooling control**
   - Takes the huge mass (=cooling storage capacity) and slow reaction speed into account.
   - Driven by multi-day weather forecasts.
- **Cooling-enable and weather inputs**
   - Reads from a binary entity whether cooling is enabled.
   - Uses a Home Assistant weather entity for daily forecasts.
- **Building tuning controls**
   - Tune overall cooling level, forecast reaction strength, and thermal storage persistence to match the building's thermal mass and cooling behavior.
- **Scheduled automatic updates**
   - Updates the output value in 6 hour steps with a limit on how much each step may increase or decrease the previous value.
   - Changed settings are applied immediately without waiting for the step interval end.
- **Runtime-configurable entities**
   - Number entities for forecast thresholds, output min/max, output step limit, charge target scale, and the abovementioned tuning controls.
- **Manual override**
   - Manual output override for forcing a specific value.
- **Diagnostic sensors**
   - Exposes output %, heat score, charge estimate, charge target, override state, status, and time until the next automatic update.

### Other Features

- **Multiple instances:** Run independent controllers for different thermostat zones or for thermostat plus CCA control.
- **Fully UI-configured:** Multi-step options wizard, no YAML required.

## Installation & Usage

For installation instructions, configuration guides, and troubleshooting info please **visit the [documentation website](https://ha-pi-thermostat-cca-control.helgeklein.com/).**

### Setting Up a Development Environment

Please see [this blog post](https://helgeklein.com/blog/developing-custom-integrations-for-home-assistant-getting-started/) for details on how to set up your own development environment for this integration (or even for Home Assistant integrations in general).
