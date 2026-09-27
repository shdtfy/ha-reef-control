"""Sensor platform for Reef Control."""
from __future__ import annotations
from datetime import datetime, timedelta

from homeassistant.components.sensor import SensorEntity
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN, EntityCategory
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity import EntityCategory
from homeassistant.core import callback

from .const import *

async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([
        ReefControlAquariumSensor(entry), ReefControlOperatingStatusSensor(hass,entry),
        ReefControlRemainingTimeSensor(hass,entry),
        ReefControlParameterStatusSensor(hass,entry,"temperature"),
        ReefControlParameterStatusSensor(hass,entry,"ph"),
        ReefControlParameterStatusSensor(hass,entry,"salinity"),
        ReefControlIcpConnectionSensor(hass,entry),
        ReefControlIcpSensor(hass,entry),
        ReefControlOverallStatusSensor(hass,entry),
    ])

class ReefControlBaseSensor(SensorEntity):
    _attr_has_entity_name=True
    def __init__(self,entry): self._entry=entry
    @property
    def device_info(self): return DeviceInfo(identifiers={(DOMAIN,self._entry.entry_id)},name=self._entry.data[CONF_AQUARIUM_NAME],manufacturer="Reef Control",model="Reef Aquarium",sw_version=VERSION)

class ReefControlAquariumSensor(ReefControlBaseSensor):
    _attr_icon="mdi:fishbowl-outline"
    def __init__(self,entry): super().__init__(entry); self._attr_unique_id=f"{entry.entry_id}_aquarium"; self._attr_name="Aquarium"
    @property
    def native_value(self): return self._entry.data[CONF_AQUARIUM_NAME]
    @property
    def extra_state_attributes(self): return {"volume_l":self._entry.data[CONF_VOLUME],"tank_type":self._entry.data.get(CONF_TANK_TYPE,"mixed_reef"),"supply_system":self._entry.data.get(CONF_SUPPLY_SYSTEM,"none"),"reef_method":self._entry.data.get(CONF_REEF_METHOD,"none"),"reef_control_version":VERSION}

class ReefControlRuntimeSensor(ReefControlBaseSensor):
    def __init__(self,hass,entry): super().__init__(entry); self.hass=hass; self._remove_interval=None
    async def async_added_to_hass(self):
        @callback
        def _update(_now=None): self.async_write_ha_state()
        self._remove_interval=async_track_time_interval(self.hass,_update,timedelta(seconds=2))
    async def async_will_remove_from_hass(self):
        if self._remove_interval: self._remove_interval(); self._remove_interval=None
    def _runtime(self): return self.hass.data.get(DOMAIN,{}).get(self._entry.entry_id,{})

class ReefControlOperatingStatusSensor(ReefControlRuntimeSensor):
    def __init__(self,hass,entry): super().__init__(hass,entry); self._attr_unique_id=f"{entry.entry_id}_feeding_status"; self._attr_name="Betriebsstatus"
    @property
    def native_value(self):
        r=self._runtime()
        if r.get("maintenance_active"): return "Wartung"
        if r.get("feeding_active"): return "Fütterung"
        until=r.get("skimmer_delay_until")
        if until and until>datetime.now().astimezone(): return "Abschäumer-Verzögerung"
        return "Normalbetrieb"
    @property
    def icon(self): return {"Wartung":"mdi:tools","Fütterung":"mdi:fish","Abschäumer-Verzögerung":"mdi:timer-sand"}.get(self.native_value,"mdi:check-circle-outline")

class ReefControlRemainingTimeSensor(ReefControlRuntimeSensor):
    _attr_icon="mdi:timer-outline"
    def __init__(self,hass,entry): super().__init__(hass,entry); self._attr_unique_id=f"{entry.entry_id}_feeding_remaining"; self._attr_name="Restzeit"
    @property
    def native_value(self):
        r=self._runtime()
        if r.get("maintenance_active"): return "00:00"
        target=r.get("feeding_until") if r.get("feeding_active") else r.get("skimmer_delay_until")
        if not target:return "00:00"
        remaining=max(0,int((target-datetime.now().astimezone()).total_seconds())); m,s=divmod(remaining,60); return f"{m:02d}:{s:02d}"

PARAMS={
 "temperature":(CONF_TEMPERATURE_ENTITY,"Temperatur","mdi:thermometer",CONF_TEMPERATURE_MIN,CONF_TEMPERATURE_MAX,CONF_TEMPERATURE_CRITICAL_MIN,CONF_TEMPERATURE_CRITICAL_MAX,DEFAULT_TEMPERATURE_MIN,DEFAULT_TEMPERATURE_MAX,DEFAULT_TEMPERATURE_CRITICAL_MIN,DEFAULT_TEMPERATURE_CRITICAL_MAX),
 "ph":(CONF_PH_ENTITY,"pH","mdi:ph",CONF_PH_MIN,CONF_PH_MAX,CONF_PH_CRITICAL_MIN,CONF_PH_CRITICAL_MAX,DEFAULT_PH_MIN,DEFAULT_PH_MAX,DEFAULT_PH_CRITICAL_MIN,DEFAULT_PH_CRITICAL_MAX),
 "salinity":(CONF_SALINITY_ENTITY,"Salinität","mdi:waves",CONF_SALINITY_MIN,CONF_SALINITY_MAX,CONF_SALINITY_CRITICAL_MIN,CONF_SALINITY_CRITICAL_MAX,DEFAULT_SALINITY_MIN,DEFAULT_SALINITY_MAX,DEFAULT_SALINITY_CRITICAL_MIN,DEFAULT_SALINITY_CRITICAL_MAX),
}

def evaluate(hass,entry,param):
    ent,name,icon,min_k,max_k,cmin_k,cmax_k,dmin,dmax,dcmin,dcmax=PARAMS[param]
    entity_id=entry.options.get(ent)
    if not entity_id:return ("Nicht konfiguriert",None,{})
    st=hass.states.get(entity_id)
    if st is None or st.state in (STATE_UNKNOWN,STATE_UNAVAILABLE):return ("Nicht verfügbar",None,{"source_entity":entity_id})
    try:value=float(st.state.replace(",","."))
    except (ValueError,TypeError):return ("Nicht verfügbar",None,{"source_entity":entity_id,"raw_state":st.state})
    mn=float(entry.options.get(min_k,dmin)); mx=float(entry.options.get(max_k,dmax)); cmn=float(entry.options.get(cmin_k,dcmin)); cmx=float(entry.options.get(cmax_k,dcmax))
    if value<cmn: status="Kritisch niedrig"
    elif value>cmx: status="Kritisch hoch"
    elif value<mn: status="Zu niedrig"
    elif value>mx: status="Zu hoch"
    else: status="Normal"
    return status,value,{"source_entity":entity_id,"value":value,"unit":st.attributes.get("unit_of_measurement"),"minimum":mn,"maximum":mx,"critical_minimum":cmn,"critical_maximum":cmx}

class ReefControlParameterStatusSensor(ReefControlRuntimeSensor):
    def __init__(self,hass,entry,param): super().__init__(hass,entry); self.param=param; self._attr_unique_id=f"{entry.entry_id}_{param}_status"; self._attr_name=PARAMS[param][1]
    @property
    def native_value(self): return evaluate(self.hass,self._entry,self.param)[0]
    @property
    def extra_state_attributes(self): return evaluate(self.hass,self._entry,self.param)[2]
    @property
    def icon(self):
        status=self.native_value
        if status.startswith("Kritisch"): return "mdi:alert-octagon"
        if status in ("Zu niedrig","Zu hoch"): return "mdi:alert"
        if status=="Normal": return PARAMS[self.param][2]
        return "mdi:help-circle-outline"

def _icp_snapshot(hass, entry):
    """Return only the important summary data from the linked Reef ICP aquarium."""
    selected = entry.options.get(CONF_REEF_ICP_ENTRY)
    if not selected:
        return {
            "connected": False,
            "status": "Nicht konfiguriert",
            "aquarium": None,
            "provider": None,
            "analysis_date": None,
            "issue_count": 0,
            "affected": [],
        }

    icp_entry = hass.config_entries.async_get_entry(selected)
    if icp_entry is None:
        return {
            "connected": False,
            "status": "Nicht verfügbar",
            "aquarium": None,
            "provider": None,
            "analysis_date": None,
            "issue_count": 0,
            "affected": [],
        }

    registry = er.async_get(hass)
    registry_entries = er.async_entries_for_config_entry(registry, selected)

    # Reef ICP exposes its compact analysis summary through the report entity.
    report_state = None
    for reg in registry_entries:
        if reg.unique_id == f"{selected}_report":
            report_state = hass.states.get(reg.entity_id)
            break

    # Fallback for older Reef ICP versions: locate the summary entity by attributes.
    if report_state is None:
        for reg in registry_entries:
            state = hass.states.get(reg.entity_id)
            if state is None:
                continue
            attrs = state.attributes
            if "status_counts" in attrs and "measurements" in attrs:
                report_state = state
                break

    if report_state is None:
        return {
            "connected": True,
            "status": "Keine Analyse",
            "entry_id": selected,
            "aquarium": icp_entry.title,
            "provider": None,
            "analysis_date": None,
            "issue_count": 0,
            "affected": [],
        }

    if report_state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE):
        return {
            "connected": True,
            "status": "Nicht verfügbar",
            "entry_id": selected,
            "aquarium": icp_entry.title,
            "provider": None,
            "analysis_date": None,
            "issue_count": 0,
            "affected": [],
        }

    attrs = report_state.attributes

    analysis_date = attrs.get("analysis_date")
    analysis_age_days = None
    if analysis_date:
        try:
            parsed_date = datetime.fromisoformat(str(analysis_date)).date()
            analysis_age_days = max(
                0, (datetime.now().astimezone().date() - parsed_date).days
            )
        except (TypeError, ValueError):
            analysis_age_days = None

    raw_status = str(report_state.state).lower()
    status = {
        "ok": "Gut",
        "good": "Gut",
        "warning": "Auffällig",
        "critical": "Kritisch",
        "unknown": "Unklar",
    }.get(raw_status, str(report_state.state))

    status_counts = attrs.get("status_counts") or {}
    try:
        issue_count = int(status_counts.get("warning", 0) or 0) + int(
            status_counts.get("critical", 0) or 0
        )
    except (TypeError, ValueError):
        issue_count = 0

    affected = []
    for measurement in attrs.get("measurements") or []:
        if not isinstance(measurement, dict):
            continue
        measurement_status = measurement.get("status") or {}
        if isinstance(measurement_status, dict):
            severity = str(measurement_status.get("severity") or "").lower()
        else:
            severity = str(measurement_status).lower()

        if severity not in ("warning", "critical"):
            continue

        name = measurement.get("name") or measurement.get("key")
        if name and str(name) not in affected:
            affected.append(str(name))

    return {
        "connected": True,
        "status": status,
        "entry_id": selected,
        "aquarium": icp_entry.title,
        "provider": attrs.get("provider_name") or attrs.get("provider"),
        "analysis_date": analysis_date,
        "analysis_age_days": analysis_age_days,
        "issue_count": issue_count,
        "affected": affected,
    }


class ReefControlIcpConnectionSensor(ReefControlRuntimeSensor):
    _attr_name="Reef ICP"
    _attr_entity_category=EntityCategory.DIAGNOSTIC
    def __init__(self,hass,entry):
        super().__init__(hass,entry); self._attr_unique_id=f"{entry.entry_id}_reef_icp_connection"
    @property
    def native_value(self):
        return "Verbunden" if _icp_snapshot(self.hass,self._entry)["connected"] else "Nicht verbunden"
    @property
    def icon(self):
        return "mdi:link-variant" if self.native_value=="Verbunden" else "mdi:link-variant-off"
    @property
    def extra_state_attributes(self):
        snap=_icp_snapshot(self.hass,self._entry)
        return {
            "aquarium": snap.get("aquarium"),
            "entry_id": snap.get("entry_id"),
            "status": snap.get("status"),
            "provider": snap.get("provider"),
            "analysis_date": snap.get("analysis_date"),
        }

class ReefControlIcpSensor(ReefControlRuntimeSensor):
    _attr_name="ICP"
    _attr_icon="mdi:flask-outline"
    def __init__(self,hass,entry):
        super().__init__(hass,entry); self._attr_unique_id=f"{entry.entry_id}_reef_icp"
    @property
    def native_value(self): return _icp_snapshot(self.hass,self._entry)["status"]
    @property
    def extra_state_attributes(self):
        snap=_icp_snapshot(self.hass,self._entry)
        return {
            "aquarium": snap.get("aquarium"),
            "provider": snap.get("provider"),
            "analysis_date": snap.get("analysis_date"),
            "analysis_age_days": snap.get("analysis_age_days"),
            "issue_count": snap.get("issue_count", 0),
            "affected": snap.get("affected", []),
        }

class ReefControlOverallStatusSensor(ReefControlRuntimeSensor):
    _attr_name="Gesamtstatus"
    def __init__(self,hass,entry): super().__init__(hass,entry); self._attr_unique_id=f"{entry.entry_id}_overall_status"
    def _results(self): return {p:evaluate(self.hass,self._entry,p)[0] for p in PARAMS}
    @property
    def native_value(self):
        vals=list(self._results().values()); active=[v for v in vals if v!="Nicht konfiguriert"]
        snap=_icp_snapshot(self.hass,self._entry)
        icp=snap["status"] if snap["connected"] else "Nicht konfiguriert"
        if not active and icp=="Nicht konfiguriert":return "Keine Messwerte"
        if any(v.startswith("Kritisch") for v in active) or icp=="Kritisch":return "Kritisch"
        if any(v in ("Zu niedrig","Zu hoch","Nicht verfügbar") for v in active) or icp in ("Auffällig","Nicht verfügbar"):return "Warnung"
        return "OK"
    @property
    def icon(self): return {"OK":"mdi:check-circle","Warnung":"mdi:alert","Kritisch":"mdi:alert-octagon","Keine Messwerte":"mdi:gauge-empty"}.get(self.native_value,"mdi:gauge")
    @property
    def extra_state_attributes(self):
        results=self._results(); snap=_icp_snapshot(self.hass,self._entry)
        icp=snap["status"] if snap["connected"] else "Nicht konfiguriert"
        issues=[f"{p}: {s}" for p,s in results.items() if s not in ("Normal","Nicht konfiguriert")]
        if icp not in ("Gut","Nicht konfiguriert","Keine Analyse"): issues.append(f"ICP: {icp}")
        return {"temperature":results["temperature"],"ph":results["ph"],"salinity":results["salinity"],"icp":icp,"issues":issues}
