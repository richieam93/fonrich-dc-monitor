from __future__ import annotations

import re

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_ENABLE_ARC_INTENSITY,
    CONF_ENABLE_ALARM_MASKS,
    CONF_ENABLE_ENERGY,
    CONF_ENABLE_HISTORY,
    CONF_ENABLE_POWER,
    DEFAULT_ENABLE_ALARM_MASKS,
    DEFAULT_ENABLE_ENERGY,
    DEFAULT_ENABLE_HISTORY,
    DEFAULT_ENABLE_POWER,
)
from .coordinator import FonrichHub
from .entity import FonrichEntity
from .registers import ALL_SENSOR_REGISTERS, RegisterDescription

_CHANNEL_RE = re.compile(r"^ch(\d+)_")


def _channel_from_key(key: str) -> int | None:
    match = _CHANNEL_RE.match(key)
    return int(match.group(1)) if match else None


def _is_enabled_for_controller(controller, key: str) -> bool:
    channel = _channel_from_key(key)
    return channel is None or channel <= int(controller.channel_count)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    hub: FonrichHub = entry.runtime_data
    entities = []
    for controller in hub.controllers:
        for description in ALL_SENSOR_REGISTERS:
            if not _is_enabled_for_controller(controller, description.key):
                continue
            if description.category == "arc_intensity" and not hub.options.get(CONF_ENABLE_ARC_INTENSITY, False):
                continue
            if description.category == "power" and not hub.options.get(CONF_ENABLE_POWER, DEFAULT_ENABLE_POWER):
                continue
            if description.category == "energy" and not hub.options.get(CONF_ENABLE_ENERGY, DEFAULT_ENABLE_ENERGY):
                continue
            if description.category == "history" and not hub.options.get(CONF_ENABLE_HISTORY, DEFAULT_ENABLE_HISTORY):
                continue
            if description.key.endswith("_mask") and not hub.options.get(CONF_ENABLE_ALARM_MASKS, DEFAULT_ENABLE_ALARM_MASKS):
                continue
            entities.append(FonrichSensor(hub, controller, description))
    async_add_entities(entities)


class FonrichSensor(FonrichEntity, SensorEntity):
    def __init__(self, hub: FonrichHub, controller, description: RegisterDescription) -> None:
        super().__init__(hub, controller, description.key)
        self.entity_description = description
        self.channel = _channel_from_key(description.key)
        self._attr_unique_id = f"{hub.gateway_uid}_{controller.controller_id}_{description.key}"
        self._attr_translation_key = description.key
        self._attr_name = self._name_with_channel_description(description.name)
        self._attr_native_unit_of_measurement = description.unit
        self._attr_device_class = description.device_class
        self._attr_state_class = description.state_class
        self._attr_suggested_display_precision = description.precision

    def _name_with_channel_description(self, name: str) -> str:
        if self.channel is None:
            return name
        channel_description = self.controller.channel_description(self.channel)
        if not channel_description or channel_description.lower() == f"kanal {self.channel}".lower():
            return name
        return f"{name} - {channel_description}"

    @property
    def native_value(self):
        return self.hub.get_value(self.controller_id, self.key)

    @property
    def extra_state_attributes(self):
        if self.channel is None:
            return None
        return {
            "channel": self.channel,
            "channel_description": self.controller.channel_description(self.channel),
            "controller_slave": self.controller.slave,
        }
