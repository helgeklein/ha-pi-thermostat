---
layout: default
title: CCA Mode UI Configuration Entities
nav_order: 6
description: "Runtime configuration entities for CCA mode in PI Thermostat & CCA Control for Home Assistant."
permalink: /ui-configuration-entities-cca/
---

# CCA Mode UI Configuration Entities

In addition to the configuration settings managed through the wizard, CCA mode can be fine-tuned at runtime via entities on the device page. Changes take effect immediately without requiring a restart.

## Switches

### Enabled

Master **on/off switch** for the CCA controller. When off, the controller is disabled and output is set to 0 %. Turning it back on resumes normal operation.

### Manual Override Enabled

Enables or disables manual override. When enabled, the CCA controller still tracks its internal automatic state, but the published output is replaced with the manual output value.

## Number Entities

### Manual Output

The output percentage used while manual override is enabled.

- **Range:** 0–100 %
- **Default:** 0 %

### Update Interval

How often the CCA controller is allowed to perform a new automatic control step, in minutes. The coordinator still wakes up once per minute to refresh state and countdown sensors.

- **Range:** 10–1440 minutes
- **Default:** 360 minutes

### Hot Day Threshold

The daytime temperature threshold above which forecast highs start increasing the CCA heat score.

- **Range:** 10.0–45.0 °C
- **Default:** 26.0 °C

### Warm Night Threshold

The nighttime temperature threshold above which forecast lows start increasing the CCA heat score.

- **Range:** 0.0–35.0 °C
- **Default:** 18.0 °C

### Output Minimum

The minimum automatic output percentage whenever the CCA controller decides cooling is needed.

- **Range:** 0–100 %
- **Default:** 10 %

### Output Maximum

The maximum automatic output percentage the CCA controller may command.

- **Range:** 0–100 %
- **Default:** 100 %

### Forecast Response Strength

High-level tuning control for how strongly hot forecasts increase the need for cooling.

- **Range:** 60–140 %
- **Default:** 100 %

### Thermal Storage Persistence

High-level tuning control for how long stored cooling is assumed to remain effective in the building core.

- **Range:** 60–140 %
- **Default:** 100 %

### Output Step Limit

Limits how much the automatic CCA output is allowed to change in a single automatic update.

- **Range:** 1–100 %
- **Default:** 10 %

### Charge Target Scale

Adjusts the overall cooling target level for a given forecast. Higher values make the controller aim for more stored cooling; lower values make it aim for less.

- **Range:** 0–200 %
- **Default:** 100 %

## Sensors (Read-Only)

### Output

The current CCA controller output as a percentage (0–100 %). This is the main output value for automations controlling valves, cooling circuits, or related equipment.

### Current Mode

The current controller mode reported by the coordinator, typically `cooling` or `off` in CCA mode.

### Heat Score

The normalized forecast-derived heat score used by the CCA controller to estimate upcoming cooling demand.

### Charge Estimate

The controller's current estimate of how much cooling is already stored in the building core.

### Charge Target

The target stored-cooling level derived from the current forecast.

### Override Active

Shows whether manual override is currently active.

### Status

The current CCA state, such as `active`, `inactive`, `forecast_hold`, `forecast_unavailable`, or `manual_override`.

### Next Update In

The remaining time in minutes until the next automatic CCA control step is due.

## Next Steps

After configuration, see the [Troubleshooting Guide]({{ '/troubleshooting/' | relative_url }}) for common issues and solutions.
