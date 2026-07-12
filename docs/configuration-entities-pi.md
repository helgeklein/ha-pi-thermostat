---
layout: default
title: PI Mode UI Configuration Entities
nav_order: 5
description: "Runtime configuration entities for PI mode in PI Thermostat & CCA Control for Home Assistant."
permalink: /ui-configuration-entities-pi/
---

# PI Mode UI Configuration Entities

In addition to the configuration settings managed through the wizard, PI mode can be fine-tuned at runtime via entities on the device page. Changes take effect immediately without requiring a restart.

## Controls

This section is only shown wen PI mode is configured to use a built-in target setpoint (i.e., when the target temperature is not read from a climate entity or set externally).

### Target Temperature

This control appears only when target temperature mode is set to "Built-in setpoint" in the configuration wizard. It uses Home Assistant's temperature device class, so it automatically displays in the user's configured unit system (°C or °F).

- **Range:** 5.0–35.0 °C
- **Default:** 20.0 °C

## Sensors

### Output

The current PI controller output as a percentage (0–100 %). This is the main output value. Use it in automations to control physical actuators like valves, heaters, or fans.

### Current Mode

The controller's current operating direction, typically `heating`, `cooling`, or `off`.

### Deviation

The current control deviation: target temperature minus current temperature (in heating mode) or current temperature minus target temperature (in cooling mode). Measured in °C.

### Current Temperature

The temperature reading currently used by the PI controller.

### Target Temperature Sensor

When target temperature mode is set to use an external entity or a climate entity, the effective target temperature is also exposed as a read-only sensor.

## Configuration

### Enabled

Master **on/off switch** for the PI controller. When off, the controller is paused. Turning it back on resumes normal operation.

### Proportional Band

The temperature range (in Kelvin) over which the PI output spans from 0 to 100 %. A smaller proportional band means more aggressive control; a larger band means smoother, less responsive control.

- **Range:** 0.5–30.0 K
- **Default:** 4.0 K

### Integral Time

The integral (reset) time in minutes. Controls how quickly the integral action eliminates steady-state deviation. A shorter time means faster correction but more risk of oscillation.

- **Range:** 1–600 minutes
- **Default:** 120 minutes

### Output Minimum

The minimum output percentage. The PI controller's output will never go below this value (unless the controller is disabled or shut down).

- **Range:** 0–100 %
- **Default:** 0 %

### Output Maximum

The maximum output percentage. The PI controller's output will never exceed this value.

- **Range:** 0–100 %
- **Default:** 100 %

### Update Interval

How often the PI controller recalculates the output, in seconds.

- **Range:** 10–600 seconds
- **Default:** 60 seconds

## Diagnostic

### Proportional Term

The proportional component of the PI output. Shows how much of the output is due to the current deviation.

### Integral Term

The integral component of the PI output. Shows how much of the output is due to accumulated past deviation. This value is persisted across restarts via Home Assistant's `RestoreEntity` mechanism.

## Next Steps

After configuration, see the [Troubleshooting Guide]({{ '/troubleshooting/' | relative_url }}) for common issues and solutions.