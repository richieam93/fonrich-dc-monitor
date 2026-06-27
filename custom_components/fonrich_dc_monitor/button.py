from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import FonrichHub
from .entity import FonrichEntity
from .registers import BUTTONS, ButtonDescription

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    hub: FonrichHub = entry.runtime_data
    async_add_entities(
        FonrichButton(hub, controller, description)
        for controller in hub.controllers
        for description in BUTTONS
    )

class FonrichButton(FonrichEntity, ButtonEntity):
    def __init__(self, hub: FonrichHub, controller, description: ButtonDescription) -> None:
        super().__init__(hub, controller, description.key)
        self.description = description
        self._attr_unique_id = f"{controller.controller_id}_{description.key}"
        self._attr_name = description.name

    async def async_press(self) -> None:
        await self.hub.write_register(self.controller, self.description.address, self.description.value)
