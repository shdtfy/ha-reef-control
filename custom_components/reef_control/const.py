"""Constants for Reef Control."""

DOMAIN = "reef_control"
VERSION = "0.1.0"

DEFAULT_AQUARIUM_NAME = "My Reef"

CONF_AQUARIUM_NAME = "aquarium_name"
CONF_VOLUME = "volume"
CONF_TANK_TYPE = "tank_type"
CONF_SUPPLY_SYSTEM = "supply_system"
CONF_REEF_METHOD = "reef_method"

# Water parameter entity assignments
CONF_TEMPERATURE_ENTITY = "temperature_entity"
CONF_PH_ENTITY = "ph_entity"
CONF_SALINITY_ENTITY = "salinity_entity"

# Equipment entity assignments
CONF_SKIMMER_ENTITY = "skimmer_entity"
CONF_RETURN_PUMP_ENTITY = "return_pump_entity"
CONF_FLOW_PUMP_ENTITY = "flow_pump_entity"
CONF_UVC_ENTITY = "uvc_entity"
CONF_LIGHT_ENTITY = "light_entity"
CONF_HEATER_ENTITY = "heater_entity"
CONF_ATO_ENTITY = "ato_entity"

# Feeding mode
CONF_FEEDING_DURATION = "feeding_duration"
CONF_SKIMMER_DELAY = "skimmer_delay"
CONF_FEEDING_PAUSE_SKIMMER = "feeding_pause_skimmer"
CONF_FEEDING_PAUSE_RETURN_PUMP = "feeding_pause_return_pump"
CONF_FEEDING_PAUSE_FLOW_PUMP = "feeding_pause_flow_pump"
CONF_FEEDING_PAUSE_UVC = "feeding_pause_uvc"
CONF_FEEDING_PAUSE_ATO = "feeding_pause_ato"

DEFAULT_FEEDING_DURATION = 10
DEFAULT_SKIMMER_DELAY = 5

# Maintenance mode
CONF_MAINTENANCE_PAUSE_SKIMMER = "maintenance_pause_skimmer"
CONF_MAINTENANCE_PAUSE_RETURN_PUMP = "maintenance_pause_return_pump"
CONF_MAINTENANCE_PAUSE_FLOW_PUMP = "maintenance_pause_flow_pump"
CONF_MAINTENANCE_PAUSE_UVC = "maintenance_pause_uvc"
CONF_MAINTENANCE_PAUSE_ATO = "maintenance_pause_ato"
CONF_MAINTENANCE_PAUSE_HEATER = "maintenance_pause_heater"
CONF_MAINTENANCE_PAUSE_LIGHT = "maintenance_pause_light"

PLATFORMS = ["sensor", "switch"]
