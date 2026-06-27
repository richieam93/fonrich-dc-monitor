from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import FonrichHub
from .entity import FonrichEntity
from .registers import BINARY_DESCRIPTIONS, BinaryDescription

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    hub: FonrichHub = entry.runtime_data
    async_add_entities(
        FonrichBinarySensor(hub, controller, description)
        for controller in hub.controllers
        for description in BINARY_DESCRIPTIONS
    )

class FonrichBinarySensor(FonrichEntity, BinarySensorEntity):
    def __init__(self, hub: FonrichHub, controller, description: BinaryDescription) -> None:
        super().__init__(hub, controller, description.key)
        self.description = description
        self._attr_unique_id = f"{controller.controller_id}_{description.key}"
        self._attr_name = description.name
        self._attr_device_class = description.device_class

    @property
    def is_on(self) -> bool | None:
        raw = self.hub.get_raw_value(self.controller_id, self.description.source_key)
        if raw is None:
            return None
        return (raw & self.description.mask) > 0
