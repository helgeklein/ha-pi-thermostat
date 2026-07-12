---
layout: default
title: CCA Mode UI Configuration Entities
nav_order: 6
description: "Runtime configuration entities for CCA mode in PI Thermostat & CCA Control for Home Assistant."
permalink: /ui-configuration-entities-cca/
---

# CCA Mode UI Configuration Entities

In addition to the configuration settings managed through the wizard, CCA mode can be fine-tuned at runtime via entities on the device page. Changes take effect immediately without requiring a restart.

For background on how CCA mode works internally and how these values relate to the algorithm, see [CCA Control Mode]({{ '/cca-control-mode/' | relative_url }}).

## Controls

### Manual Override

Enables or disables manual override. When enabled, the CCA controller still tracks its internal automatic state, but the published output is replaced with the manual output value.

### Manual Output

The output percentage used while manual override is enabled.

- **Range:** 0–100 %
- **Default:** 0 %

## Sensors

### Output

The current CCA controller output as a percentage (0–100 %). This is the main output value for automations controlling physical actuators like valves.

### Current Mode

The current controller mode reported by the coordinator, typically `cooling` or `off`.

## Configuration

### Enabled

Master **on/off switch** for the CCA controller. When off, the controller is disabled and output is set to 0 %. Turning it back on resumes normal operation.

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
- **Default:** 0 %

### Output Maximum

The maximum automatic output percentage the CCA controller may command.

- **Range:** 0–100 %
- **Default:** 60 %

### Forecast Response Strength

High-level tuning control for how strongly hot forecasts increase the need for cooling.

- **Range:** 60–140 %
- **Default:** 100 %

### Thermal Storage Persistence

High-level tuning control for how long stored cooling is assumed to remain effective in the building core.

- **Range:** 60–140 %
- **Default:** 100 %

### Output Step Limit

Limits how much the automatic CCA output is allowed to change in a single update interval.

- **Range:** 1–100 %
- **Default:** 10 %

### Charge Target Scale

Adjusts the overall cooling target level for a given forecast. Higher values make the controller aim for more stored cooling; lower values make it aim for less.

- **Range:** 0–200 %
- **Default:** 100 %

## Diagnostic

### Charge Target

The calculated target output before the controller takes the estimated current charge into account. The controller first derives this value from the forecast, then subtracts the estimated current charge, and finally applies step limiting and output min/max limits.

### Charge Target (Before Scaling)

The normalized forecast-based demand value before the configured charge target scale is applied. Internally, this is the controller's heat score, which is then converted into the final charge target.

### Current Charge (Est.)

The controller's current estimate of how much cooling is already stored in the building core. This internal state is advanced on automatic CCA control steps and then retained between steps.

### Override Active

Shows whether manual override is currently active. Possible values are `on` and `off`.

### Status

The current CCA state. Possible values are `idle`, `inactive`, `forecast_hold`, `forecast_unavailable`, `active`, and `manual_override`.

### Next Update In

The remaining time in minutes until the next automatic CCA control step is due. This countdown is only shown while cooling is enabled.

## Next Steps

After configuration, see [CCA Control Mode]({{ '/cca-control-mode/' | relative_url }}) for the algorithm overview, or the [Troubleshooting Guide]({{ '/troubleshooting/' | relative_url }}) for common issues and solutions.
