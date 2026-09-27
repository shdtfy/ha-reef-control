<p align="center">
  <img src="images/logo.png" alt="Reef Control" width="520">
</p>

# 🪸 Reef Control

**Aquarium monitoring, management & automation for Home Assistant**

Reef Control is a custom Home Assistant integration for bringing a reef
aquarium into Home Assistant as a real control system, not just a
collection of sensor values.

It combines aquarium monitoring, equipment control, operating modes and
automatic control logic in one integration. Reef Control can also be
linked with **Reef ICP** so laboratory analysis data and day-to-day
aquarium control can work together.

> **Current version:** `0.3.0`\
> **Status:** Active development

------------------------------------------------------------------------

## ✨ What Reef Control does

Reef Control creates a central Home Assistant device for your aquarium
and lets you connect the equipment and sensors that already exist in
Home Assistant.

### Currently implemented

-   🐠 Multiple aquarium configuration
-   🔌 Assignment of existing Home Assistant equipment entities
-   🌡️ Temperature sensor integration
-   🧪 pH and salinity sensor integration
-   💧 Manual water values for KH, calcium, magnesium, nitrate and
    phosphate
-   🚦 Configurable monitoring and critical limits
-   🐟 Feeding mode
-   🛠️ Maintenance mode
-   🌡️ Automatic heater control
-   🧪 Optional Reef ICP connection
-   🇩🇪 German and 🇬🇧 English configuration interface

------------------------------------------------------------------------

## 🎛️ Equipment & entities

Reef Control does not require proprietary aquarium hardware.

Instead, you assign existing Home Assistant entities to the aquarium.

Currently supported equipment includes:

  Equipment            Purpose
  -------------------- ------------------------------------------------
  Protein skimmer      Automatic pause/restart during operating modes
  Return pump          Feeding and maintenance control
  Flow pump            Feeding and maintenance control
  UV-C sterilizer      Operating-mode control
  Aquarium lighting    Maintenance control
  Heater               Automatic temperature control
  Auto top-off (ATO)   Feeding and maintenance control

This means switches, smart plugs, relays or devices from other Home
Assistant integrations can become part of Reef Control.

------------------------------------------------------------------------

## 💧 Water values

Reef Control can combine continuously measured values with manually
entered measurements.

### Sensor values

-   Temperature
-   pH
-   Salinity

### Manual measurements

-   Alkalinity / KH
-   Calcium
-   Magnesium
-   Nitrate
-   Phosphate

When Reef ICP is connected, Reef Control can also use the latest
available ICP values as an additional source.

The goal is to create one coherent aquarium state from several different
measurement sources.

------------------------------------------------------------------------

## 🚦 Monitoring limits

Individual limits can be configured for monitored water parameters.

For temperature, pH and salinity, Reef Control distinguishes between:

-   normal minimum
-   normal maximum
-   critical minimum
-   critical maximum

This allows Home Assistant to distinguish between a value that is merely
outside the preferred range and one that has reached a critical level.

------------------------------------------------------------------------

## 🌡️ Automatic temperature control

Temperature control is the first full automatic control loop in Reef
Control.

Assign a temperature sensor and heater entity, enable temperature
control and Reef Control can operate the heater automatically.

### Configurable parameters

-   **Target temperature**
-   **Hysteresis**
-   **Minimum heater run time**
-   **Minimum heater off time**

Example:

With a target temperature of **25.0 °C** and a hysteresis of **0.3 °C**,
Reef Control can switch the heater on at **24.7 °C or below** and switch
it off again at **25.0 °C or above**.

Minimum on/off times prevent rapid switching.

The controller also handles states such as:

-   Heating
-   Target range
-   Paused
-   Waiting for minimum interval
-   Sensor error
-   Heater error
-   Not configured

During maintenance mode, automatic temperature control is paused.

------------------------------------------------------------------------

## 🐟 Feeding mode

Feeding mode can temporarily stop selected aquarium equipment.

You can configure whether Reef Control pauses:

-   Protein skimmer
-   Return pump
-   Flow pump
-   UV-C
-   Auto top-off

The feeding duration is configurable.

A separate **skimmer restart delay** can be used so the protein skimmer
does not immediately restart when feeding mode ends.

After feeding, Reef Control restores the equipment that was previously
running.

------------------------------------------------------------------------

## 🛠️ Maintenance mode

Maintenance mode provides a central switch for temporarily shutting down
equipment while working on the aquarium.

Depending on your configuration, it can pause:

-   Protein skimmer
-   Return pump
-   Flow pump
-   UV-C
-   Auto top-off
-   Heater
-   Aquarium lighting

When maintenance mode ends, Reef Control restores the relevant equipment
and resumes temperature control when enabled.

------------------------------------------------------------------------

## 🧪 Reef ICP integration

Reef Control and **Reef ICP** are separate Home Assistant integrations
designed to work together.

### Reef ICP

Reef ICP focuses on:

-   ICP analysis storage
-   laboratory values
-   historical analyses
-   interpretation
-   element status
-   dosing recommendations

### Reef Control

Reef Control focuses on:

-   live aquarium state
-   equipment
-   operating modes
-   monitoring
-   automation
-   control loops

A Reef Control aquarium can be linked to an existing Reef ICP aquarium.
The latest ICP information can then be incorporated into Reef Control
alongside manual and live measurements.

**Reef ICP tells you what is happening in the water.\
Reef Control is being built to act on the aquarium.**

------------------------------------------------------------------------

## 📦 Installation

### HACS

Reef Control is currently installed as a custom repository.

1.  Open **HACS** in Home Assistant.
2.  Add this repository as a **Custom repository**.
3.  Select **Integration** as the repository type.
4.  Install **Reef Control**.
5.  Restart Home Assistant.
6.  Go to **Settings → Devices & services → Add integration**.
7.  Search for **Reef Control**.

Repository:

`https://github.com/shdtfy/ha-reef-control`

### Manual installation

Copy:

`custom_components/reef_control`

to:

`/config/custom_components/reef_control`

Restart Home Assistant and add Reef Control from **Devices & services**.

------------------------------------------------------------------------

## ⚙️ Initial setup

When creating an aquarium, Reef Control asks for basic information such
as:

-   Aquarium name
-   Net water volume
-   Aquarium type
-   Supply system
-   Reef method

After setup, additional configuration is available from the integration
options:

**Equipment & entities → Water values → Monitoring limits → Operating
modes → Temperature control → Reef ICP**

This keeps the initial setup small while allowing the aquarium
controller to grow with the system.

------------------------------------------------------------------------

## 🗺️ Direction of the project

Reef Control is under active development.

The project is moving from aquarium monitoring toward a modular aquarium
controller inside Home Assistant.

Planned and experimental areas include:

-   additional automatic control loops
-   smarter ATO management
-   lighting control
-   dosing integration
-   safety interlocks
-   alarm and notification logic
-   richer aquarium status evaluation
-   tighter Reef ICP interaction
-   dedicated Reef Control dashboard/card
-   additional equipment types

The guiding principle is simple:

> **Use the devices and sensors already available in Home Assistant and
> add aquarium-specific intelligence on top.**

------------------------------------------------------------------------

## 🧩 Home Assistant philosophy

Reef Control is intentionally designed around Home Assistant entities
rather than one specific hardware ecosystem.

A heater does not need to be a "Reef Control heater".\
A pump does not need a special Reef Control protocol.

If Home Assistant can control or read the device, Reef Control should
increasingly be able to use it as part of the aquarium.

That makes it possible to combine equipment from different manufacturers
into one aquarium control layer.

------------------------------------------------------------------------

## 📸 Screenshots

Screenshots of the configuration, aquarium entities and future Reef
Control dashboard will be added as development progresses.

------------------------------------------------------------------------

## ⚠️ Development status

Reef Control is still in active development.

Automatic control of aquarium equipment can affect livestock and
aquarium safety. Verify entity assignments, limits and controller
behaviour carefully before relying on automation unattended.

Home Assistant, Reef Control and connected smart devices should not be
treated as a replacement for appropriate independent safety mechanisms
where equipment failure could cause damage.

------------------------------------------------------------------------

## 🐛 Issues & feedback

Found a bug or have an idea for Reef Control?

Use the GitHub issue tracker:

`https://github.com/shdtfy/ha-reef-control/issues`

Feature suggestions and real-world testing are welcome, especially for
different combinations of aquarium equipment and Home Assistant
integrations.

------------------------------------------------------------------------

## 👨‍💻 Author

**Filo Mahlich**

Reef Control is an independent open-source project for Home Assistant.

------------------------------------------------------------------------

### 🪸 Reef Control

**Monitor. Manage. Automate.**
