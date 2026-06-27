from __future__ import annotations

import re

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_ENABLE_ALARM_BINARY_SENSORS,
    CONF_SENSOR_PROFILE,
    DEFAULT_ENABLE_ALARM_BINARY_SENSORS,
    DEFAULT_SENSOR_PROFILE,
    SENSOR_PROFILE_DIAGNOSTIC,
    SENSOR_PROFILE_STANDARD,
)
from .coordinator import FonrichHub
from .entity import FonrichEntity
from .registers import BINARY_DESCRIPTIONS, BinaryDescription

_CHANNEL_RE = re.compile(r"^ch(\d+)_")


def _channel_from_key(key: str) -> int | None:
    match = _CHANNEL_RE.match(key)
    return int(match.group(1)) if match else None


def _binary_sensors_enabled(hub: FonrichHub) -> bool:
    profile = str(hub.options.get(CONF_SENSOR_PROFILE, DEFAULT_SENSOR_PROFILE))
    return bool(
        hub.options.get(CONF_ENABLE_ALARM_BINARY_SENSORS, DEFAULT_ENABLE_ALARM_BINARY_SENSORS)
        or profile in {SENSOR_PROFILE_STANDARD, SENSOR_PROFILE_DIAGNOSTIC}
    )


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    hub: FonrichHub = entry.runtime_data
    if not _binary_sensors_enabled(hub):
        return
    entities = []
    for controller in hub.controllers:
        for description in BINARY_DESCRIPTIONS:
            channel = _channel_from_key(description.key)
            if channel is not None and channel > int(controller.channel_count):
                continue
            entities.append(FonrichBinarySensor(hub, controller, description))
    async_add_entities(entities)


class FonrichBinarySensor(FonrichEntity, BinarySensorEntity):
    def __init__(self, hub: FonrichHub, controller, description: BinaryDescription) -> None:
        super().__init__(hub, controller, description.key)
        self.description = description
        self.channel = _channel_from_key(description.key)
        self._attr_unique_id = f"{hub.gateway_uid}_{controller.controller_id}_{description.key}"
        self._attr_name = self._name_with_channel_description(description.name)
        self._attr_device_class = description.device_class

    def _name_with_channel_description(self, name: str) -> str:
        if self.channel is None:
            return name
        suffix = re.sub(rf"^Kanal\s+{self.channel}\s*", "", name).strip()
        channel_description = self.controller.channel_description(self.channel).strip()
        if channel_description and channel_description.lower() != f"kanal {self.channel}".lower():
            return f"Kanal {self.channel:02d} - {channel_description} {suffix}".strip()
        return f"Kanal {self.channel:02d} {suffix}".strip()

    @property
    def is_on(self) -> bool | None:
        raw = self.hub.get_raw_value(self.controller_id, self.description.source_key)
        if raw is None:
            return None
        return (raw & self.description.mask) > 0

    @property
    def extra_state_attributes(self):
        if self.channel is None:
            return None
        return {
            "channel": self.channel,
            "channel_description": self.controller.channel_description(self.channel),
            "controller_slave": self.controller.slave,
        }
