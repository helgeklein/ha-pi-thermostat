---
layout: default
title: Home
nav_order: 1
description: "A Home Assistant custom integration that implements a PI (proportional–integral) controller for precise temperature regulation."
permalink: /
---

# PI Thermostat for Home Assistant

[![Test status](https://github.com/helgeklein/ha-pi-thermostat/actions/workflows/test.yml/badge.svg)](https://github.com/helgeklein/ha-pi-thermostat/actions/workflows/test.yml)
[![Test coverage](https://raw.githubusercontent.com/helgeklein/ha-pi-thermostat/main/.github/badges/coverage.svg)](https://github.com/helgeklein/ha-pi-thermostat/actions/workflows/test.yml)

A Home Assistant custom integration that implements a **PI (proportional–integral) controller** for precise temperature regulation. It calculates a heating or cooling output percentage based on the difference between a target temperature and a measured current temperature, and exposes the result as a sensor for use in automations.

## Features

- **PI control algorithm** — Industry-standard proportional–integral controller powered by the [simple-pid](https://pypi.org/project/simple-pid/) library. Tunable proportional band and integral time, adjustable at runtime.
- **Flexible temperature sources** — Read the current temperature from a temperature sensor or a climate entity. Set the target temperature via a built-in setpoint, an external entity, or a climate entity.
- **Operating modes** — Heating only, cooling only, or auto (heat + cool). In auto mode, the direction is determined from a climate entity's HVAC action.
- **Output sensor** — The PI output (0–100 %) is exposed as a sensor entity for use in automations controlling valves, heaters, fans, etc.
- **Sensor fault handling** — Shut down immediately or hold the last output for a grace period when the temperature sensor becomes unavailable.
- **I-term persistence** — The integral term is saved across restarts. Configurable startup modes: last persisted, fixed value, or zero.
- **Runtime-configurable entities** — Number entities for proportional band, integral time, target temperature, output min/max, and update interval. Enabled switch to pause/resume.
- **Diagnostic sensors** — Output %, deviation, proportional term, integral term.
- **Multiple instances** — Run independent thermostat controllers for different zones.
- **Fully UI-configured** — Three-step options wizard, no YAML required.
- **Rich language support** — Chinese, Dutch, English, French, German, Italian, Polish, Portuguese, Spanish, Swedish.

---

<div class="center">
  <a href="installation-download" class="btn">Get Started →</a>
</div>