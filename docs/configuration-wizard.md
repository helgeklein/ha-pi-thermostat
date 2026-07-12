---
layout: default
title: Configuration Wizard
nav_order: 4
description: "Configuration wizard guide for PI Thermostat & CCA Control for Home Assistant."
permalink: /configuration-wizard/
---

# Configuration Wizard

The integration's settings are managed via a multi-step wizard. To invoke the configuration wizard:

1. Go to **Settings** → **Devices & Services**.
2. Find **PI Thermostat & CCA Control**.
3. Click the **gear icon** to open the configuration wizard.

**Notes**

- The configuration wizard can be canceled at any time. When you do that, no changes are made to the configuration.
- The configuration wizard can be invoked as often as needed to inspect the configuration or make changes to it.

The options flow is mode-aware:

- **PI mode path:** Controller mode → Climate entity & operating mode → Temperature sensors & target → Sensor fault & startup mode
- **CCA mode path:** Controller mode → CCA data sources

## Step 1: Controller Mode

Choose which controller the integration should run:

- **PI** — the room-temperature PI controller for heating, cooling, or auto mode.
- **CCA** — the forecast-driven controller for concrete core activation cooling.

The remaining steps depend on this selection.

## PI Mode

### Step 2: Climate Entity & Operating Mode

### Climate Entity (Optional)

If you have a climate entity (e.g., from a smart thermostat or HVAC system), you can configure it here. When configured, the climate entity can serve as a source for:

- **Current temperature** — used as fallback when no dedicated temperature sensor is configured.
- **Target temperature** — when target temperature mode is set to "From climate entity".
- **Heating/cooling direction** — required when operating mode is "Heat + Cool (auto)".
- **Auto-disable** — optionally set output to 0 % when the climate entity's HVAC mode is "off".

### Operating Mode

Determines how the controller decides between heating and cooling:

- **Heat + Cool (auto):** The controller reads the HVAC action (heating/cooling) from the configured climate entity and adjusts the output direction accordingly. Requires a climate entity.
- **Heat only:** The controller always operates in heating mode. Positive deviation (target > actual) produces positive output.
- **Cool only:** The controller always operates in cooling mode. Positive deviation (actual > target) produces positive output.

### Auto-Disable on HVAC Off

When enabled and a climate entity is configured, the controller's output is set to 0 % whenever the climate entity's HVAC mode is "off".

### Step 3: Temperature Sensors & Target

### Temperature Sensor (Optional)

Select a temperature sensor entity to provide the current temperature reading. This is optional if a climate entity is configured (falls back to the climate entity's `current_temperature` attribute).

**Note:** At least one temperature source is required — either a dedicated temperature sensor or a climate entity.

### Target Temperature Mode

Where to read the target (setpoint) temperature from:

- **Built-in setpoint:** Use the integration's own target temperature number entity. This is the simplest option — adjust the target directly from the device page.
- **External entity:** Read the target temperature from another entity (e.g., an `input_number` helper). Useful for sharing a setpoint across multiple zones or automations.
- **From climate entity:** Use the climate entity's target temperature. Only available when a climate entity is configured.

### Target Temperature Entity

Only used when the target temperature mode is "External entity". Select the entity to read the target temperature from.

### Step 4: Sensor Fault & Startup Mode

### Sensor Fault Mode

Behavior when the temperature sensor becomes unavailable:

- **Shutdown immediately:** Set output to 0 % right away. Safest option for most scenarios.
- **Hold last output:** Maintain the last calculated output for a 30-minute grace period, then shut down. Useful for short sensor dropouts.

### Output Startup Mode

How the integral term (and thus the output) is initialized when the integration starts:

- **Last persisted:** Restore the integral term from before the last restart. Falls back to the startup value if no saved state exists.
- **Fixed value:** Always start with the configured startup value.
- **Zero:** Always start at 0 %.

### Output Startup Value

The output percentage to use on startup. Used as the initial value when startup mode is "Fixed value", or as the fallback when mode is "Last persisted" and no previous value exists. Range: 0–100 %.

## CCA Mode

### Step 2: CCA Data Sources

This step configures the inputs the CCA controller needs for forecast-driven cooling.

### Cooling Enable Entity

Select an entity that indicates whether cooling is currently allowed. Supported entity types are binary sensors, switches, and input booleans.

The CCA controller only produces cooling output while this signal indicates that cooling is enabled.

### Cooling Enable On

Defines which state of the cooling-enable entity means "cooling enabled":

- **On:** Cooling is enabled when the selected entity is on.
- **Off:** Cooling is enabled when the selected entity is off.

This is useful when the source signal uses inverted logic.

### Weather Entity

Select the Home Assistant weather entity that provides the daily forecast used by the CCA controller.

The selected weather entity must support daily forecasts.

### Forecast Horizon Days

How many forecast days the CCA controller should consider when computing its heat score and cooling target.

Smaller values make the controller focus more on the near-term forecast. Larger values make it consider a longer upcoming warm period.

### Forecast Unavailable Mode

Behavior when no usable forecast is available:

- **Hold:** Keep using the last automatic CCA output.
- **Shutdown:** Set the CCA output to 0 %.

If you want more background on how CCA uses forecasts, stored cooling, and scheduled update steps, see [CCA Control Mode]({{ '/cca-control-mode/' | relative_url }}).

### Validation Notes

The CCA data-source step validates that:

- a cooling-enable entity is configured
- a weather entity is configured
- the weather entity supports daily forecasts

## Next Steps

After the configuration wizard, take a look at the runtime-configuration guide for your selected mode:

- [PI mode UI configuration entities]({{ '/ui-configuration-entities-pi/' | relative_url }})
- [CCA mode UI configuration entities]({{ '/ui-configuration-entities-cca/' | relative_url }})
- [CCA control mode background and algorithm]({{ '/cca-control-mode/' | relative_url }})