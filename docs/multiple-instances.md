---
layout: default
title: Multiple Instances
nav_order: 7
description: "Configuring multiple instances of PI Thermostat for Home Assistant."
permalink: /multiple-instances/
---

# Multiple Instances

The integration supports multiple instances. This is useful for controlling different zones or heating/cooling circuits with independent PI controllers.

## Creating Instances

After the initial installation, additional integration instances can be created on the integration page by clicking **Add entry** > **Submit**. In the **Device created** dialog, specify a name that helps you distinguish the instances (see below for examples), then click **Finish**.

## Entity ID Names

The names of an instance's entity IDs are constructed by Home Assistant from the following components:

- Entity type (e.g., `sensor`)
- Device name (e.g., `PI Thermostat Living Room`)
- Entity name (e.g., `Output`)

The example above would result in the entity ID: `sensor.pi_thermostat_living_room_output`.

## Use Case Examples

### Multi-Zone Heating

#### Requirements

You have underfloor heating in two zones with different thermal characteristics:

- **Living room:** Large room with lots of glazing — needs aggressive control with a narrow proportional band.
- **Bedroom:** Small, well-insulated room — needs gentler control with a wider proportional band.

#### Configuration

1. On the integration page, rename the default integration entry from `PI Thermostat` to `Living Room`.
2. Create a second instance of the integration named `Bedroom`.
3. Configure each instance with its own temperature sensor, target temperature, and PI tuning parameters.

### Heating and Cooling

#### Requirements

You have separate heating and cooling systems for the same zone (e.g., radiator + ceiling fan).

#### Configuration

1. Set up one instance in **Heat only** mode for the radiator valve.
2. Set up a second instance in **Cool only** mode for the fan.
3. Each instance writes to its own output entity, which drives the respective actuator via automations.

