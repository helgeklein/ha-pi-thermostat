# PI Thermostat for Home Assistant

[![Test status](https://github.com/helgeklein/ha-pi-thermostat/actions/workflows/test.yml/badge.svg)](https://github.com/helgeklein/ha-pi-thermostat/actions/workflows/test.yml)
[![Test coverage](https://raw.githubusercontent.com/helgeklein/ha-pi-thermostat/main/.github/badges/coverage.svg)](https://github.com/helgeklein/ha-pi-thermostat/actions/workflows/test.yml)

A Home Assistant custom integration that implements a **PI (proportional–integral) controller** for precise temperature regulation. It calculates a heating or cooling output percentage based on the difference between a target temperature and a measured current temperature, then writes the result to an output entity for use in automations.

## Features

- **PI control algorithm:**
    - Industry-standard proportional–integral controller (PID with Kd=0).
    - Powered by the [simple-pid](https://pypi.org/project/simple-pid/) library.
    - Tunable proportional band (K) and integral time (minutes) — adjustable at runtime.
    - Anti-windup protection and output clamping (configurable min/max %).
- **Flexible temperature sources:**
    - Read the current temperature from a **temperature sensor** or a **climate entity**.
    - Target temperature via **built-in setpoint**, **external entity**, or **climate entity**.
- **Operating modes:**
    - **Heating only**, **cooling only**, or **auto (heat + cool)**.
    - In auto mode, the heating/cooling direction is read from a climate entity's HVAC action.
    - Optional auto-disable when the climate entity's HVAC mode is "off".
- **Output control:**
    - Write the PI output (0–100 %) to an `input_number` or `number` entity.
    - Use the output value in automations to control valves, heaters, fans, etc.
- **Sensor fault handling:**
    - **Shutdown immediately:** Set output to 0 % when the temperature sensor becomes unavailable.
    - **Hold last output:** Maintain the last output for a 5-minute grace period, then shut down.
- **I-term persistence across restarts:**
    - Configurable startup modes: **last persisted**, **fixed value**, or **zero**.
    - The integral term is saved via Home Assistant's `RestoreEntity` mechanism.
- **Runtime-configurable entities:**
    - Number entities for proportional band, integral time, target temperature, output min/max, and update interval — all adjustable without reconfiguring.
    - Enabled switch to pause/resume the controller.
- **Diagnostic sensors:**
    - Output %, control error, proportional term, integral term.
    - Binary sensor indicating whether the controller is active (output > 0 %).
- **Multiple instances:** Run independent thermostat controllers for different zones.
- **Fully UI-configured:** Three-step options wizard, no YAML required.
- **Rich language support:** UI translations available for Chinese, Dutch, English, French, German, Italian, Polish, Portuguese, Spanish, Swedish.

## Configuration

The integration is configured via a three-step options wizard:

1. **Climate entity & operating mode** — optional climate entity, heat/cool/auto mode, auto-disable on HVAC off.
2. **Temperature sensors & target** — temperature sensor, target temperature mode (built-in, external entity, or climate entity).
3. **Output & fault handling** — output entity, sensor fault mode, I-term startup mode and value.

PI tuning parameters and other runtime settings are adjusted directly via number entities on the device page.

## Installation & Usage

For installation instructions, configuration guides, and troubleshooting info please **visit the [documentation website](https://ha-pi-thermostat.helgeklein.com/).**

## Developer Information

This repository contains the source code for the integration. For user documentation and guides, please visit the [documentation website](https://ha-pi-thermostat.helgeklein.com/).

### Setting Up a Development Environment

Please see [this blog post](https://helgeklein.com/blog/developing-custom-integrations-for-home-assistant-getting-started/) for details on how to set up your own development environment for this integration (or even for Home Assistant integrations in general).
