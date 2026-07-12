---
layout: default
title: CCA Control Mode
nav_order: 7
description: "Background and algorithm overview for CCA mode in PI Thermostat & CCA Control for Home Assistant."
permalink: /cca-control-mode/
---

# CCA Control Mode

This page explains the background and internal logic of **CCA mode**. For setup details, see the [Configuration Wizard]({{ '/configuration-wizard/' | relative_url }}) and [CCA Mode UI Configuration Entities]({{ '/ui-configuration-entities-cca/' | relative_url }}).

## What CCA Mode Is Trying to Do

CCA mode is designed for **concrete core activation cooling** and other very slow cooling systems with a lot of thermal mass.

These systems behave differently from a normal room thermostat:

- they react slowly
- they store cooling in the building structure
- they need to act before the room temperature becomes uncomfortable

Because of that, CCA mode does **not** control directly from the current room temperature like the PI controller does. Instead, it uses the weather forecast to estimate how much cooling should be built up in advance.

## Main Inputs

CCA mode uses three main inputs:

- **Cooling enable signal**
  - A binary sensor, switch, or input boolean tells the controller whether cooling is currently allowed.
- **Daily weather forecast**
  - The configured weather entity provides forecast highs and lows for the coming days.
- **Runtime tuning settings**
  - Forecast thresholds, update interval, output limits, charge target scale, forecast response strength, and thermal storage persistence shape how strongly the controller reacts.

## High-Level Model

The controller works with three closely related internal values:

- **Charge Target (Before Scaling)**
  - The forecast-based demand level before the configured charge-target scale is applied.
  - Internally, this is the controller's heat score.
- **Charge Target**
  - The raw output target derived from the forecast after scaling.
- **Current Charge (Est.)**
  - The controller's estimate of how much cooling is already stored in the building core.

The basic idea is simple:

- hot forecasts increase the target
- stored cooling reduces the need for more output
- the final output is limited so it cannot jump too much or exceed configured bounds

## How Forecasts Become Cooling Demand

For each forecast day, CCA mode looks at:

- the forecast high temperature
- the forecast low temperature

From those two values it builds a normalized demand score:

- hotter days increase the score
- warmer nights also increase the score
- the scores are averaged across the configured forecast horizon

This is why the two forecast threshold settings matter:

- **Hot Day Threshold** decides when daytime highs start to count as a cooling signal.
- **Warm Night Threshold** decides when nighttime lows start to count as a cooling signal.

## How Charge Target Is Calculated

Once the forecast-based demand is known, the controller converts it into a **Charge Target**.

The most important setting here is:

- **Charge Target Scale**
  - Raises or lowers the overall target level for the same forecast.

In practice:

- higher scale means the controller aims for more cooling overall
- lower scale means it aims for less

## How Stored Cooling Is Taken Into Account

CCA mode does not assume every new forecast requires starting from zero. It keeps a running estimate of how much cooling is already stored.

That estimate is shown as:

- **Current Charge (Est.)**

On each automatic control step, the controller:

1. starts from the previous estimated charge
2. adds the effect of the previous automatic output
3. subtracts the effect of forecasted heat demand

This is where the two high-level tuning sliders come in:

- **Forecast Response Strength**
  - Changes how strongly forecast heat pushes the controller toward more cooling.
- **Thermal Storage Persistence**
  - Changes how long stored cooling is assumed to remain effective.

In practical terms:

- a more responsive setting reacts more strongly to hot weather
- a more persistent setting assumes cooling stays in the building longer

## How Output Is Derived

The controller first calculates a raw need for cooling by comparing:

- **Charge Target**
- **Current Charge (Est.)**

If the target is above the estimated current charge, more cooling is needed. If the building is already charged enough, less cooling is needed.

After that, the controller applies these limits:

- **Output Step Limit**
  - Prevents large jumps between automatic control steps.
- **Output Minimum** and **Output Maximum**
  - Keep the automatic output within the configured range.

If **Manual Override** is enabled, the published output is replaced with the manual output value, but the controller still keeps tracking its internal automatic state.

## Update Timing

CCA mode uses two different time layers:

- **Coordinator heartbeat**
  - Runs every minute so Home Assistant can refresh state and countdown information.
- **Update Interval**
  - Controls when a new automatic CCA control step is actually allowed.

This means the UI can update frequently even though the main CCA calculation only advances on a much slower schedule, such as every 6 hours.

The sensor **Next Update In** shows how long remains until the next automatic step is due.

## What Happens Between Scheduled Steps

Between scheduled CCA steps, the controller normally keeps using its cached state.

Some setting changes still take effect immediately:

- manual override changes
- output min/max clamping of cached output
- certain forecast-driven tuning changes such as charge-target scale

Those immediate refreshes update the published result without consuming the next scheduled automatic step.

## Forecast-Unavailable Behavior

If the weather forecast cannot be used, CCA mode falls back to the configured behavior:

- **Hold**
  - Reuse the last automatic output.
- **Shutdown**
  - Force the output to `0 %`.

The **Status** sensor shows whether the controller is active, inactive, holding forecast output, unavailable due to forecast problems, or running in manual override.

## Reading the Main CCA Sensors

When diagnosing behavior, these sensors usually matter most:

- **Output**
  - The value you typically use in automations.
- **Charge Target (Before Scaling)**
  - The raw forecast-driven demand level.
- **Charge Target**
  - The scaled target the controller is working toward.
- **Current Charge (Est.)**
  - How much cooling the controller thinks is already stored.
- **Status**
  - Whether the controller is active, inactive, holding output, unavailable, or in manual override.
- **Next Update In**
  - When the next scheduled automatic step will happen.

## Tuning Strategy

For practical tuning, start in this order:

1. **Charge Target Scale**
   - Set the overall cooling level for the building.
2. **Forecast Response Strength**
   - Decide how strongly hot forecasts should push the controller.
3. **Thermal Storage Persistence**
   - Match how long cooling really lasts in the building.

Then fine-tune:

- **Hot Day Threshold** and **Warm Night Threshold** to define when weather starts to matter
- **Output Minimum**, **Output Maximum**, and **Output Step Limit** to shape how the automatic output behaves in practice

## Related Pages

- [Configuration Wizard]({{ '/configuration-wizard/' | relative_url }})
- [CCA Mode UI Configuration Entities]({{ '/ui-configuration-entities-cca/' | relative_url }})
- [Troubleshooting Guide]({{ '/troubleshooting/' | relative_url }})