from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import FonrichHub
from .entity import FonrichEntity
from .registers import ALL_SENSOR_REGISTERS, RegisterDescription

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    hub: FonrichHub = entry.runtime_data
    entities = []
    for controller in hub.controllers:
        for description in ALL_SENSOR_REGISTERS:
            if description.category == "arc_intensity" and not hub.options.get("enable_arc_intensity", False):
                continue
            entities.append(FonrichSensor(hub, controller, description))
    async_add_entities(entities)

class FonrichSensor(FonrichEntity, SensorEntity):
    def __init__(self, hub: FonrichHub, controller, description: RegisterDescription) -> None:
        super().__init__(hub, controller, description.key)
        self.entity_description = description
        self._attr_unique_id = f"{controller.controller_id}_{description.key}"
        self._attr_translation_key = description.key
        self._attr_name = description.name
        self._attr_native_unit_of_measurement = description.unit
        self._attr_device_class = description.device_class
        self._attr_state_class = description.state_class
        self._attr_suggested_display_precision = description.precision

    @property
    def native_value(self):
        return self.hub.get_value(self.controller_id, self.key)
