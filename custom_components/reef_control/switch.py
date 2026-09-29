"""Switch platform for Reef Control."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.event import async_track_state_change_event

from .const import *


async def async_setup_entry(hass, entry, async_add_entities):
    feeding = ReefControlFeedingModeSwitch(hass, entry)
    maintenance = ReefControlMaintenanceModeSwitch(hass, entry)
    temperature = ReefControlTemperatureControlSwitch(hass, entry)
    ato = ReefControlAtoControlSwitch(hass, entry)
    runtime = hass.data.setdefault(DOMAIN, {}).setdefault(entry.entry_id, {"entry": entry})
    runtime.update(
        {
            "feeding_switch": feeding,
            "maintenance_switch": maintenance,
            "temperature_control_switch": temperature,
            "ato_control_switch": ato,
        }
    )
    runtime.setdefault("feeding_active", False)
    runtime.setdefault("feeding_until", None)
    runtime.setdefault("skimmer_delay_until", None)
    runtime.setdefault("maintenance_active", False)
    runtime.setdefault("temperature_control_status", "Deaktiviert")
    runtime.setdefault("ato_control_status", "Deaktiviert")
    async_add_entities([feeding, maintenance, temperature, ato])


class ReefControlBaseSwitch(SwitchEntity):
    _attr_has_entity_name = True

    def __init__(self, hass, entry):
        self.hass = hass
        self._entry = entry
        self._is_on = False
        self._restore_states = {}

    @property
    def is_on(self):
        return self._is_on

    @property
    def device_info(self):
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.entry_id)},
            name=self._entry.data[CONF_AQUARIUM_NAME],
            manufacturer="Reef Control",
            model="Reef Aquarium",
            sw_version=VERSION,
        )

    def _runtime(self):
        return self.hass.data.setdefault(DOMAIN, {}).setdefault(
            self._entry.entry_id, {"entry": self._entry}
        )

    def _entities(self, plural_key, legacy_key=None):
        return get_entity_list(self._entry.options, plural_key, legacy_key)

    async def _set(self, entity_id, on):
        state = self.hass.states.get(entity_id)
        if not state or state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE):
            return
        await self.hass.services.async_call(
            entity_id.split(".", 1)[0],
            "turn_on" if on else "turn_off",
            {"entity_id": entity_id},
            blocking=True,
        )

    async def _set_many(self, entity_ids, on):
        for entity_id in entity_ids:
            await self._set(entity_id, on)

    async def _pause_entities(self, ids, force_restore_on=None):
        force_restore_on = force_restore_on or set()
        self._restore_states = {}
        for entity_id in dict.fromkeys(ids):
            state = self.hass.states.get(entity_id)
            if not state:
                continue
            was_on = state.state == STATE_ON or entity_id in force_restore_on
            self._restore_states[entity_id] = was_on
            if state.state == STATE_ON:
                await self._set(entity_id, False)

    async def _restore_entities(self, skip_ids=None):
        skip_ids = skip_ids or set()
        for entity_id, was_on in list(self._restore_states.items()):
            if was_on and entity_id not in skip_ids:
                await self._set(entity_id, True)
        self._restore_states = {}


class ReefControlFeedingModeSwitch(ReefControlBaseSwitch):
    _attr_name = "Fütterungsmodus"
    _attr_icon = "mdi:fish"

    def __init__(self, hass, entry):
        super().__init__(hass, entry)
        self._attr_unique_id = f"{entry.entry_id}_feeding_mode"
        self._auto_off_task = None
        self._skimmer_task = None
        self._pending_skimmer_ids = set()

    def _skimmers(self):
        return self._entities(CONF_SKIMMER_ENTITIES, CONF_SKIMMER_ENTITY)

    def _ato_entities(self):
        return self._entities(CONF_ATO_ENTITIES, CONF_ATO_ENTITY)

    async def async_turn_on(self, **kwargs):
        if self._is_on:
            return
        runtime = self._runtime()
        maintenance = runtime.get("maintenance_switch")
        if maintenance and maintenance.is_on:
            await maintenance.async_turn_off()

        pending_skimmers = self.cancel_skimmer_delay()
        self._cancel_auto_off_task()
        self._is_on = True
        duration = float(
            self._entry.options.get(CONF_FEEDING_DURATION, DEFAULT_FEEDING_DURATION)
        )
        runtime["feeding_active"] = True
        runtime["feeding_until"] = datetime.now().astimezone() + timedelta(minutes=duration)
        runtime["maintenance_active"] = False
        self.async_write_ha_state()

        await self._pause_entities(
            self._feeding_pause_entities(), force_restore_on=pending_skimmers
        )
        self._auto_off_task = self.hass.async_create_task(
            self._auto_turn_off(duration * 60)
        )

    async def async_turn_off(self, **kwargs):
        if not self._is_on:
            return
        self._cancel_auto_off_task()
        self._is_on = False
        runtime = self._runtime()
        runtime["feeding_active"] = False
        runtime["feeding_until"] = None
        self.async_write_ha_state()

        skimmers = set(self._skimmers())
        ato_ids = set(self._ato_entities())
        ato_controller = runtime.get("ato_control_switch")

        for entity_id, was_on in list(self._restore_states.items()):
            if not was_on or entity_id in skimmers:
                continue
            if entity_id in ato_ids and ato_controller and ato_controller.is_on:
                continue
            await self._set(entity_id, True)

        restore_skimmers = [
            entity_id
            for entity_id in skimmers
            if self._restore_states.get(entity_id)
        ]
        if restore_skimmers:
            delay = float(self._entry.options.get(CONF_SKIMMER_DELAY, DEFAULT_SKIMMER_DELAY))
            if delay > 0:
                runtime["skimmer_delay_until"] = datetime.now().astimezone() + timedelta(
                    minutes=delay
                )
                self._pending_skimmer_ids = set(restore_skimmers)
                self._skimmer_task = self.hass.async_create_task(
                    self._delayed_turn_on(restore_skimmers, delay * 60)
                )
            else:
                runtime["skimmer_delay_until"] = None
                await self._set_many(restore_skimmers, True)
        else:
            runtime["skimmer_delay_until"] = None

        self._restore_states = {}
        if ato_controller and ato_controller.is_on:
            await ato_controller.async_evaluate()

    async def async_will_remove_from_hass(self):
        self._cancel_auto_off_task()
        self.cancel_skimmer_delay()

    def cancel_skimmer_delay(self):
        pending = (
            set(self._pending_skimmer_ids)
            if self._skimmer_task and not self._skimmer_task.done()
            else set()
        )
        if self._skimmer_task and not self._skimmer_task.done():
            self._skimmer_task.cancel()
        self._skimmer_task = None
        self._pending_skimmer_ids = set()
        self._runtime()["skimmer_delay_until"] = None
        return pending

    def _feeding_pause_entities(self):
        options = self._entry.options
        groups = (
            (CONF_SKIMMER_ENTITIES, CONF_SKIMMER_ENTITY, CONF_FEEDING_PAUSE_SKIMMER, True),
            (CONF_RETURN_PUMP_ENTITIES, CONF_RETURN_PUMP_ENTITY, CONF_FEEDING_PAUSE_RETURN_PUMP, False),
            (CONF_FLOW_PUMP_ENTITIES, CONF_FLOW_PUMP_ENTITY, CONF_FEEDING_PAUSE_FLOW_PUMP, True),
            (CONF_UVC_ENTITIES, CONF_UVC_ENTITY, CONF_FEEDING_PAUSE_UVC, False),
            (CONF_ATO_ENTITIES, CONF_ATO_ENTITY, CONF_FEEDING_PAUSE_ATO, True),
            (CONF_CALCIUM_REACTOR_ENTITIES, None, CONF_FEEDING_PAUSE_CALCIUM_REACTOR, False),
        )
        result = []
        for plural_key, legacy_key, flag, default in groups:
            if options.get(flag, default):
                result.extend(get_entity_list(options, plural_key, legacy_key))
        return list(dict.fromkeys(result))

    async def _auto_turn_off(self, seconds):
        try:
            await asyncio.sleep(seconds)
            await self.async_turn_off()
        except asyncio.CancelledError:
            pass

    async def _delayed_turn_on(self, entity_ids, seconds):
        try:
            await asyncio.sleep(seconds)
            await self._set_many(entity_ids, True)
        except asyncio.CancelledError:
            pass
        finally:
            self._runtime()["skimmer_delay_until"] = None
            self._pending_skimmer_ids = set()
            self._skimmer_task = None

    def _cancel_auto_off_task(self):
        if self._auto_off_task and not self._auto_off_task.done():
            self._auto_off_task.cancel()
        self._auto_off_task = None


class ReefControlMaintenanceModeSwitch(ReefControlBaseSwitch):
    _attr_name = "Wartungsmodus"
    _attr_icon = "mdi:tools"

    def __init__(self, hass, entry):
        super().__init__(hass, entry)
        self._attr_unique_id = f"{entry.entry_id}_maintenance_mode"

    async def async_turn_on(self, **kwargs):
        if self._is_on:
            return
        runtime = self._runtime()
        feeding = runtime.get("feeding_switch")
        if feeding and feeding.is_on:
            await feeding.async_turn_off()
        pending_skimmers = feeding.cancel_skimmer_delay() if feeding else set()

        self._is_on = True
        runtime["maintenance_active"] = True
        runtime["feeding_active"] = False
        runtime["feeding_until"] = None
        self.async_write_ha_state()
        await self._pause_entities(
            self._maintenance_pause_entities(), force_restore_on=pending_skimmers
        )

    async def async_turn_off(self, **kwargs):
        if not self._is_on:
            return
        self._is_on = False
        runtime = self._runtime()
        runtime["maintenance_active"] = False
        self.async_write_ha_state()

        ato = runtime.get("ato_control_switch")
        ato_ids = set(self._entities(CONF_ATO_ENTITIES, CONF_ATO_ENTITY))
        await self._restore_entities(ato_ids if ato and ato.is_on else set())

        controller = runtime.get("temperature_control_switch")
        if controller and controller.is_on:
            await controller.async_evaluate()
        if ato and ato.is_on:
            await ato.async_evaluate()

    def _maintenance_pause_entities(self):
        options = self._entry.options
        groups = (
            (CONF_SKIMMER_ENTITIES, CONF_SKIMMER_ENTITY, CONF_MAINTENANCE_PAUSE_SKIMMER, True),
            (CONF_RETURN_PUMP_ENTITIES, CONF_RETURN_PUMP_ENTITY, CONF_MAINTENANCE_PAUSE_RETURN_PUMP, True),
            (CONF_FLOW_PUMP_ENTITIES, CONF_FLOW_PUMP_ENTITY, CONF_MAINTENANCE_PAUSE_FLOW_PUMP, True),
            (CONF_UVC_ENTITIES, CONF_UVC_ENTITY, CONF_MAINTENANCE_PAUSE_UVC, True),
            (CONF_ATO_ENTITIES, CONF_ATO_ENTITY, CONF_MAINTENANCE_PAUSE_ATO, True),
            (CONF_HEATER_ENTITIES, CONF_HEATER_ENTITY, CONF_MAINTENANCE_PAUSE_HEATER, True),
            (CONF_LIGHT_ENTITIES, CONF_LIGHT_ENTITY, CONF_MAINTENANCE_PAUSE_LIGHT, False),
            (CONF_CALCIUM_REACTOR_ENTITIES, None, CONF_MAINTENANCE_PAUSE_CALCIUM_REACTOR, False),
        )
        result = []
        for plural_key, legacy_key, flag, default in groups:
            if options.get(flag, default):
                result.extend(get_entity_list(options, plural_key, legacy_key))
        return list(dict.fromkeys(result))


class ReefControlTemperatureControlSwitch(ReefControlBaseSwitch):
    _attr_name = "Temperaturregelung"
    _attr_icon = "mdi:thermostat"

    def __init__(self, hass, entry):
        super().__init__(hass, entry)
        self._attr_unique_id = f"{entry.entry_id}_temperature_control"
        self._is_on = bool(
            entry.options.get(
                CONF_TEMPERATURE_CONTROL_ENABLED, DEFAULT_TEMPERATURE_CONTROL_ENABLED
            )
        )
        self._remove_listener = None
        self._last_temperature = None
        self._last_action = "Deaktiviert"
        self._last_switch_at = None
        self._last_switch_action = None
        self._pending_task = None

    def _heaters(self):
        return self._entities(CONF_HEATER_ENTITIES, CONF_HEATER_ENTITY)

    async def async_added_to_hass(self):
        sensor = self._entry.options.get(CONF_TEMPERATURE_ENTITY)
        if sensor:
            self._remove_listener = async_track_state_change_event(
                self.hass, [sensor], self._temperature_changed
            )
        if self._is_on:
            await self.async_evaluate()

    async def async_will_remove_from_hass(self):
        if self._remove_listener:
            self._remove_listener()
            self._remove_listener = None
        self._cancel_pending()

    async def _temperature_changed(self, event):
        if self._is_on:
            await self.async_evaluate()

    async def async_turn_on(self, **kwargs):
        self._is_on = True
        self.async_write_ha_state()
        await self.async_evaluate()

    async def async_turn_off(self, **kwargs):
        self._is_on = False
        self._cancel_pending()
        self._set_status("Deaktiviert")

    def _cancel_pending(self):
        if self._pending_task and not self._pending_task.done():
            self._pending_task.cancel()
        self._pending_task = None

    def _set_status(self, status):
        self._last_action = status
        self._runtime()["temperature_control_status"] = status
        self.async_write_ha_state()

    def _heater_states(self):
        result = {}
        for entity_id in self._heaters():
            state = self.hass.states.get(entity_id)
            result[entity_id] = "missing" if state is None else state.state
        return result

    def _heater_group_state(self):
        states = self._heater_states()
        if not states:
            return "not_configured"
        if any(value in ("missing", STATE_UNKNOWN, STATE_UNAVAILABLE) for value in states.values()):
            return STATE_UNAVAILABLE
        return STATE_ON if any(value == STATE_ON for value in states.values()) else STATE_OFF

    def _all_heaters_on(self):
        states = self._heater_states()
        return bool(states) and all(value == STATE_ON for value in states.values())

    def _remaining_lockout(self, want_on):
        if not self._last_switch_at:
            return 0
        minutes = float(
            self._entry.options.get(
                CONF_TEMPERATURE_MIN_OFF_TIME if want_on else CONF_TEMPERATURE_MIN_ON_TIME,
                DEFAULT_TEMPERATURE_MIN_OFF_TIME if want_on else DEFAULT_TEMPERATURE_MIN_ON_TIME,
            )
        )
        elapsed = (datetime.now().astimezone() - self._last_switch_at).total_seconds()
        return max(0, minutes * 60 - elapsed)

    async def _switch_heaters(self, on):
        await self._set_many(self._heaters(), on)
        self._last_switch_at = datetime.now().astimezone()
        self._last_switch_action = "EIN" if on else "AUS"

    async def _delayed_evaluate(self, seconds):
        try:
            await asyncio.sleep(seconds)
            self._pending_task = None
            if self._is_on:
                await self.async_evaluate()
        except asyncio.CancelledError:
            pass

    async def async_evaluate(self):
        self._cancel_pending()
        if not self._is_on:
            self._set_status("Deaktiviert")
            return

        sensor_id = self._entry.options.get(CONF_TEMPERATURE_ENTITY)
        heaters = self._heaters()
        if not sensor_id or not heaters:
            self._set_status("Nicht konfiguriert")
            return
        if self._runtime().get("maintenance_active"):
            self._set_status("Pausiert")
            return

        state = self.hass.states.get(sensor_id)
        if state is None or state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE):
            self._set_status("Sensorfehler")
            return
        try:
            temperature = float(str(state.state).replace(",", "."))
        except (TypeError, ValueError):
            self._set_status("Sensorfehler")
            return

        self._last_temperature = temperature
        heater_state = self._heater_group_state()
        if heater_state in ("not_configured", STATE_UNKNOWN, STATE_UNAVAILABLE):
            self._set_status("Heizungsfehler")
            return

        target = float(
            self._entry.options.get(CONF_TEMPERATURE_TARGET, DEFAULT_TEMPERATURE_TARGET)
        )
        hysteresis = float(
            self._entry.options.get(
                CONF_TEMPERATURE_HYSTERESIS, DEFAULT_TEMPERATURE_HYSTERESIS
            )
        )

        want_on = None
        if temperature <= target - hysteresis and not self._all_heaters_on():
            want_on = True
        elif temperature >= target and heater_state == STATE_ON:
            want_on = False

        if want_on is not None:
            remaining = self._remaining_lockout(want_on)
            if remaining > 0:
                self._set_status("Warte auf Mindestpause")
                self._pending_task = self.hass.async_create_task(
                    self._delayed_evaluate(remaining)
                )
                return
            await self._switch_heaters(want_on)
            heater_state = STATE_ON if want_on else STATE_OFF

        self._set_status("Heizen" if heater_state == STATE_ON else "Sollbereich")

    @property
    def extra_state_attributes(self):
        target = float(
            self._entry.options.get(CONF_TEMPERATURE_TARGET, DEFAULT_TEMPERATURE_TARGET)
        )
        hysteresis = float(
            self._entry.options.get(
                CONF_TEMPERATURE_HYSTERESIS, DEFAULT_TEMPERATURE_HYSTERESIS
            )
        )
        heaters = self._heaters()
        return {
            "status": self._last_action,
            "temperature": self._last_temperature,
            "target": target,
            "heating_on_below": round(target - hysteresis, 2),
            "heating_off_at": target,
            "hysteresis": hysteresis,
            "temperature_entity": self._entry.options.get(CONF_TEMPERATURE_ENTITY),
            "heater_entity": heaters[0] if heaters else None,
            "heater_entities": heaters,
            "heater_state": self._heater_group_state(),
            "heater_states": self._heater_states(),
            "last_switch_action": self._last_switch_action,
            "last_switch_at": self._last_switch_at.isoformat() if self._last_switch_at else None,
            "minimum_on_minutes": float(
                self._entry.options.get(
                    CONF_TEMPERATURE_MIN_ON_TIME, DEFAULT_TEMPERATURE_MIN_ON_TIME
                )
            ),
            "minimum_off_minutes": float(
                self._entry.options.get(
                    CONF_TEMPERATURE_MIN_OFF_TIME, DEFAULT_TEMPERATURE_MIN_OFF_TIME
                )
            ),
        }


class ReefControlAtoControlSwitch(ReefControlBaseSwitch):
    _attr_name = "Wasserstandsregelung"
    _attr_icon = "mdi:water-sync"

    def __init__(self, hass, entry):
        super().__init__(hass, entry)
        self._attr_unique_id = f"{entry.entry_id}_ato_control"
        self._is_on = bool(
            entry.options.get(CONF_ATO_CONTROL_ENABLED, DEFAULT_ATO_CONTROL_ENABLED)
        )
        self._remove_listener = None
        self._confirm_task = None
        self._max_runtime_task = None
        self._cooldown_task = None
        self._locked = False
        self._last_fill_started = None
        self._last_fill_stopped = None
        self._last_fill_duration = None
        self._last_action = None

    def _pumps(self):
        return self._entities(CONF_ATO_ENTITIES, CONF_ATO_ENTITY)

    def _pump_states(self):
        result = {}
        for entity_id in self._pumps():
            state = self.hass.states.get(entity_id)
            result[entity_id] = "missing" if state is None else state.state
        return result

    def _pump_group_state(self):
        states = self._pump_states()
        if not states:
            return "not_configured"
        if any(value in ("missing", STATE_UNKNOWN, STATE_UNAVAILABLE) for value in states.values()):
            return STATE_UNAVAILABLE
        return STATE_ON if any(value == STATE_ON for value in states.values()) else STATE_OFF

    async def async_added_to_hass(self):
        sensor = self._entry.options.get(CONF_WATER_LEVEL_ENTITY)
        if sensor:
            self._remove_listener = async_track_state_change_event(
                self.hass, [sensor], self._level_changed
            )
        await self._set_many(self._pumps(), False)
        if self._is_on:
            await self.async_evaluate()

    async def async_will_remove_from_hass(self):
        if self._remove_listener:
            self._remove_listener()
            self._remove_listener = None
        self._cancel_tasks()
        await self._set_many(self._pumps(), False)

    async def _level_changed(self, event):
        if self._is_on:
            await self.async_evaluate()

    def _cancel_task(self, name):
        task = getattr(self, name)
        if task and not task.done():
            task.cancel()
        setattr(self, name, None)

    def _cancel_tasks(self):
        for name in ("_confirm_task", "_max_runtime_task", "_cooldown_task"):
            self._cancel_task(name)

    def _set_status(self, status):
        self._last_action = status
        self._runtime()["ato_control_status"] = status
        self.async_write_ha_state()

    def _is_low(self, state):
        return state == self._entry.options.get(CONF_ATO_LOW_STATE, DEFAULT_ATO_LOW_STATE)

    async def async_turn_on(self, **kwargs):
        self._locked = False
        self._is_on = True
        self.async_write_ha_state()
        await self.async_evaluate()

    async def async_turn_off(self, **kwargs):
        self._is_on = False
        self._locked = False
        self._cancel_tasks()
        await self._stop_pumps(record=True)
        self._set_status("Deaktiviert")

    async def _confirm_low(self, seconds):
        try:
            await asyncio.sleep(seconds)
            self._confirm_task = None
            if self._is_on:
                await self.async_evaluate(confirmed=True)
        except asyncio.CancelledError:
            pass

    async def _runtime_limit(self, seconds):
        try:
            await asyncio.sleep(seconds)
            self._max_runtime_task = None
            await self._stop_pumps(record=True)
            self._locked = True
            self._set_status("Sicherheitsstopp")
        except asyncio.CancelledError:
            pass

    async def _cooldown_done(self, seconds):
        try:
            await asyncio.sleep(seconds)
            self._cooldown_task = None
            if self._is_on:
                await self.async_evaluate()
        except asyncio.CancelledError:
            pass

    async def _start_pumps(self):
        await self._set_many(self._pumps(), True)
        self._last_fill_started = datetime.now().astimezone()
        self._last_action = "Nachfüllen"
        self._cancel_task("_max_runtime_task")
        maximum = float(
            self._entry.options.get(CONF_ATO_MAX_RUNTIME, DEFAULT_ATO_MAX_RUNTIME)
        )
        self._max_runtime_task = self.hass.async_create_task(
            self._runtime_limit(maximum)
        )

    async def _stop_pumps(self, record=True):
        if self._pump_group_state() == STATE_ON:
            await self._set_many(self._pumps(), False)
        self._cancel_task("_max_runtime_task")
        if record and self._last_fill_started:
            now = datetime.now().astimezone()
            self._last_fill_stopped = now
            self._last_fill_duration = round(
                (now - self._last_fill_started).total_seconds(), 1
            )
            self._last_fill_started = None

    async def async_evaluate(self, confirmed=False):
        if not self._is_on:
            self._set_status("Deaktiviert")
            return

        sensor_id = self._entry.options.get(CONF_WATER_LEVEL_ENTITY)
        pumps = self._pumps()
        if not sensor_id or not pumps:
            self._set_status("Nicht konfiguriert")
            return
        if self._locked:
            self._set_status("Sicherheitsstopp")
            return

        runtime = self._runtime()
        if runtime.get("maintenance_active") or (
            runtime.get("feeding_active")
            and self._entry.options.get(CONF_FEEDING_PAUSE_ATO, True)
        ):
            await self._stop_pumps(record=True)
            self._cancel_task("_confirm_task")
            self._set_status("Pausiert")
            return

        level = self.hass.states.get(sensor_id)
        pump_state = self._pump_group_state()
        if level is None or level.state in (STATE_UNKNOWN, STATE_UNAVAILABLE):
            await self._stop_pumps(record=True)
            self._cancel_task("_confirm_task")
            self._set_status("Sensorfehler")
            return
        if pump_state in ("not_configured", STATE_UNKNOWN, STATE_UNAVAILABLE):
            self._cancel_tasks()
            self._set_status("Pumpenfehler")
            return

        low = self._is_low(level.state)
        if not low:
            self._cancel_task("_confirm_task")
            if pump_state == STATE_ON:
                await self._stop_pumps(record=True)
                cooldown = float(
                    self._entry.options.get(CONF_ATO_COOLDOWN, DEFAULT_ATO_COOLDOWN)
                ) * 60
                if cooldown > 0:
                    self._set_status("Wartezeit")
                    self._cooldown_task = self.hass.async_create_task(
                        self._cooldown_done(cooldown)
                    )
                    return
            self._set_status("Bereit")
            return

        if pump_state == STATE_ON:
            self._set_status("Nachfüllen")
            return
        if self._cooldown_task and not self._cooldown_task.done():
            self._set_status("Wartezeit")
            return

        delay = float(
            self._entry.options.get(CONF_ATO_CONFIRM_DELAY, DEFAULT_ATO_CONFIRM_DELAY)
        )
        if not confirmed and delay > 0:
            if not self._confirm_task:
                self._set_status("Wasserstand prüfen")
                self._confirm_task = self.hass.async_create_task(
                    self._confirm_low(delay)
                )
            return

        await self._start_pumps()
        self._set_status("Nachfüllen")

    @property
    def extra_state_attributes(self):
        sensor_id = self._entry.options.get(CONF_WATER_LEVEL_ENTITY)
        pumps = self._pumps()
        level = self.hass.states.get(sensor_id) if sensor_id else None
        return {
            "status": self._last_action,
            "locked": self._locked,
            "water_level_entity": sensor_id,
            "water_level_state": level.state if level else None,
            "low_level_state": self._entry.options.get(
                CONF_ATO_LOW_STATE, DEFAULT_ATO_LOW_STATE
            ),
            "ato_entity": pumps[0] if pumps else None,
            "ato_entities": pumps,
            "ato_state": self._pump_group_state(),
            "ato_states": self._pump_states(),
            "confirm_delay_seconds": float(
                self._entry.options.get(
                    CONF_ATO_CONFIRM_DELAY, DEFAULT_ATO_CONFIRM_DELAY
                )
            ),
            "maximum_runtime_seconds": float(
                self._entry.options.get(CONF_ATO_MAX_RUNTIME, DEFAULT_ATO_MAX_RUNTIME)
            ),
            "cooldown_minutes": float(
                self._entry.options.get(CONF_ATO_COOLDOWN, DEFAULT_ATO_COOLDOWN)
            ),
            "last_fill_started": self._last_fill_started.isoformat()
            if self._last_fill_started
            else None,
            "last_fill_stopped": self._last_fill_stopped.isoformat()
            if self._last_fill_stopped
            else None,
            "last_fill_duration_seconds": self._last_fill_duration,
        }
