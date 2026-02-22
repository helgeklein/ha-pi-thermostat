---
layout: default
title: Troubleshooting
nav_order: 6
description: "Common issues and solutions for PI Thermostat for Home Assistant."
permalink: /troubleshooting/
---

# Troubleshooting Guide

This guide helps resolve issues with the PI Thermostat integration.

## Monitoring the Integration from the UI

### Sensors

The integration comes with the following sensors that help you understand the controller's inner workings:

- **Output:** The current PI output percentage (0–100 %).
- **Deviation:** The current control deviation (target − actual temperature).
- **Proportional term:** How much of the output is due to the current temperature deviation.
- **Integral term:** How much of the output is due to accumulated past deviation.

### Checking the Output Entity

If you have configured an output entity (`input_number` or `number`), you can observe it directly in the Home Assistant UI. Its value should update on every controller cycle (default: every 60 seconds).

## Common Issues

### Output Stays at 0 %

Check the following:

1. **Enabled switch** — Make sure the integration's enabled switch is turned on.
2. **Temperature sensor** — Verify the temperature sensor entity is available and reporting values.
3. **Target temperature** — Ensure the target temperature is set (check the target temperature number entity or configured source entity).
4. **Auto-disable on HVAC off** — If enabled and a climate entity is configured, the output is 0 % when the climate entity's HVAC mode is "off".
5. **Sensor fault** — If the temperature sensor became unavailable, the controller may have shut down. Check the sensor's state.

### Output Oscillates

If the output swings rapidly between high and low values:

1. **Increase the proportional band** — A larger proportional band produces smoother control.
2. **Increase the integral time** — A longer integral time slows down the integral action, reducing oscillation.
3. **Increase the update interval** — Less frequent updates can help stabilize noisy sensors.

### Controller Overshoots

If the temperature consistently overshoots the target:

1. **Increase the proportional band** — Makes the controller less aggressive near the setpoint.
2. **Increase the integral time** — Slows the integral wind-up.
3. **Reduce the output maximum** — Limit the maximum output if full power causes overshoot.

## Debugging

### Enable Debug Logging

To enable debug logging, add the following to your `configuration.yaml`:

```yaml
logger:
  logs:
    custom_components.pi_thermostat: debug
```

Then restart Home Assistant. Debug messages will appear in the Home Assistant log.

Note that debug logging is enabled per integration instance. Log messages are prefixed with the last five characters of the instance's entry ID (e.g., `[ABC12]`) to distinguish between multiple instances.

### Log File Location

You can find the **Home Assistant Core** log at **Settings** → **Systems** → **Logs**.

### Log Message Format

- **Timestamp:** e.g., `2026-01-31 17:20:22.174`
- **Severity:** e.g., `DEBUG`
- **HA thread name:** e.g., `(MainThread)`
- **Integration instance:** e.g., `[custom_components.pi_thermostat.ABC12]`
- **Log message:** the actual log message, e.g., `PI output: 42.5%, deviation: 1.2K, P: 30.0%, I: 12.5%`

## Getting Help

### Before Seeking Help

1. **Enable debug logging** and reproduce the issue.
1. **Check the logs** to understand what's going on.
1. **Document your configuration** and the exact problem.

### Where to Get Help

1. **Documentation:** Review all sections of this documentation.
1. **GitHub Issues:** [Report a bug](https://github.com/helgeklein/ha-pi-thermostat/issues).
1. **Home Assistant Community:** [Join a forum discussion](https://community.home-assistant.io/).
