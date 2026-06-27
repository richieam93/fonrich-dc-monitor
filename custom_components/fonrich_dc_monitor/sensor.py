from __future__ import annotations

import re

from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_ENABLE_ALARM_MASKS,
    CONF_ENABLE_ALARM_TEXT_SENSOR,
    CONF_ENABLE_ARC_INTENSITY,
    CONF_ENABLE_ENERGY,
    CONF_ENABLE_HISTORY,
    CONF_ENABLE_POWER,
    CONF_SENSOR_PROFILE,
    DEFAULT_ENABLE_ALARM_MASKS,
    DEFAULT_ENABLE_ALARM_TEXT_SENSOR,
    DEFAULT_ENABLE_ENERGY,
    DEFAULT_ENABLE_HISTORY,
    DEFAULT_ENABLE_POWER,
    DEFAULT_SENSOR_PROFILE,
    SENSOR_PROFILE_DIAGNOSTIC,
    SENSOR_PROFILE_PRODUCTION,
    SENSOR_PROFILE_STANDARD,
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


def _sensor_enabled(hub: FonrichHub, description: RegisterDescription) -> bool:
    profile = str(hub.options.get(CONF_SENSOR_PROFILE, DEFAULT_SENSOR_PROFILE))

    # Production profile is intentionally lean: controller voltage, total current,
    # channel currents, channel powers and optional energy. No alarm/status clutter.
    if profile == SENSOR_PROFILE_PRODUCTION:
        if description.category in {"alarm", "diagnostic", "history", "arc_intensity"}:
            return False
    elif profile == SENSOR_PROFILE_STANDARD:
        if description.category in {"diagnostic", "arc_intensity"}:
            return False
    elif profile != SENSOR_PROFILE_DIAGNOSTIC:
        if description.category in {"diagnostic", "arc_intensity"}:
            return False

    if description.category == "power" and not hub.options.get(CONF_ENABLE_POWER, DEFAULT_ENABLE_POWER):
        return False
    if description.category == "energy" and not hub.options.get(CONF_ENABLE_ENERGY, DEFAULT_ENABLE_ENERGY):
        return False
    if description.category == "history" and not hub.options.get(CONF_ENABLE_HISTORY, DEFAULT_ENABLE_HISTORY):
        return False
    if description.category == "arc_intensity" and not hub.options.get(CONF_ENABLE_ARC_INTENSITY, False):
        return False
    if description.key.endswith("_mask") and not hub.options.get(CONF_ENABLE_ALARM_MASKS, DEFAULT_ENABLE_ALARM_MASKS):
        return False
    return True


ALARM_STATUS_1_BITS = [
    (1, "Bus Lichtbogen"),
    (2, "Kanal Lichtbogen"),
    (4, "Unterspannung"),
    (8, "Überspannung"),
    (16, "Temperatur 1 hoch"),
    (32, "Temperatur 2 hoch"),
    (64, "Kanal Rückstrom"),
    (128, "Total Rückstrom hoch"),
    (256, "Total Strom niedrig"),
    (512, "Total Strom hoch"),
    (1024, "Kanal Kein Strom"),
    (2048, "Kanal Unterstrom"),
    (4096, "Kanal Überstrom"),
    (8192, "Kanal Strom zu niedrig"),
    (16384, "Kanal Strom zu hoch"),
]

CHANNEL_MASKS = [
    ("arc_alarm_ch_1_8", "Lichtbogen"),
    ("reverse_current_alarm_mask", "Rückstrom"),
    ("no_current_alarm_mask", "Kein Strom"),
    ("undercurrent_alarm_mask", "Unterstrom"),
    ("overcurrent_alarm_mask", "Überstrom"),
    ("current_low_alarm_mask", "Strom zu niedrig"),
    ("current_high_alarm_mask", "Strom zu hoch"),
    ("arc_selfcheck_fail_mask", "Lichtbogen Selbsttest Fehler"),
]


def _alarm_text_enabled(hub: FonrichHub) -> bool:
    return bool(hub.options.get(CONF_ENABLE_ALARM_TEXT_SENSOR, DEFAULT_ENABLE_ALARM_TEXT_SENSOR))


def _short_controller_name(name: str) -> str:
    return str(name).split("/")[0].strip() or str(name)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    hub: FonrichHub = entry.runtime_data
    entities = []
    if _alarm_text_enabled(hub):
        entities.append(FonrichGatewayAlarmTextSensor(hub))
        for controller in hub.controllers:
            entities.append(FonrichControllerAlarmTextSensor(hub, controller))

    for controller in hub.controllers:
        for description in ALL_SENSOR_REGISTERS:
            if not _is_enabled_for_controller(controller, description.key):
                continue
            if not _sensor_enabled(hub, description):
                continue
            entities.append(FonrichSensor(hub, controller, description))
    async_add_entities(entities)


class FonrichSensor(FonrichEntity, SensorEntity):
    def __init__(self, hub: FonrichHub, controller, description: RegisterDescription) -> None:
        super().__init__(hub, controller, description.key)
        self.description = description
        self.entity_description = SensorEntityDescription(
            key=description.key,
            device_class=description.device_class,
            state_class=description.state_class,
            native_unit_of_measurement=description.unit,
            suggested_display_precision=description.precision,
        )
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
        suffix = re.sub(rf"^Kanal\s+{self.channel}\s*", "", name).strip()
        channel_description = self.controller.channel_description(self.channel).strip()
        if channel_description and channel_description.lower() != f"kanal {self.channel}".lower():
            return f"Kanal {self.channel:02d} - {channel_description} {suffix}".strip()
        return f"Kanal {self.channel:02d} {suffix}".strip()

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


class FonrichControllerAlarmTextSensor(FonrichEntity, SensorEntity):
    """Single compact alarm text sensor per controller."""

    def __init__(self, hub: FonrichHub, controller) -> None:
        super().__init__(hub, controller, "alarm_text")
        self.entity_description = SensorEntityDescription(key="alarm_text")
        self._attr_unique_id = f"{hub.gateway_uid}_{controller.controller_id}_alarm_text"
        self._attr_name = "Alarmmeldung"

    @property
    def native_value(self):
        messages = self._alarm_messages()
        if not messages:
            return "OK"
        text = "; ".join(messages[:4])
        if len(messages) > 4:
            text += f"; +{len(messages) - 4} weitere"
        return text[:255]

    def _alarm_messages(self) -> list[str]:
        prefix = _short_controller_name(self.controller.name)
        messages: list[str] = []

        # Channel-specific masks first, so the state is useful, e.g. "V1 Kanal 06 Lichtbogen".
        for key, label in CHANNEL_MASKS:
            raw = self.hub.get_raw_value(self.controller_id, key) or 0
            for channel in range(1, min(int(self.controller.channel_count), 16) + 1):
                if raw & (1 << (channel - 1)):
                    desc = self.controller.channel_description(channel).strip()
                    channel_text = f"Kanal {channel:02d}"
                    if desc and desc.lower() != f"kanal {channel}".lower():
                        channel_text += f" - {desc}"
                    messages.append(f"{prefix} {channel_text} {label}")

        alarm_1 = self.hub.get_raw_value(self.controller_id, "alarm_status_1") or 0
        for bit, label in ALARM_STATUS_1_BITS:
            if alarm_1 & bit:
                # If a channel-light-arc mask already gives exact channel info, skip the generic summary.
                if bit == 2 and any("Lichtbogen" in msg for msg in messages):
                    continue
                messages.append(f"{prefix} {label}")

        alarm_2 = self.hub.get_raw_value(self.controller_id, "alarm_status_2") or 0
        if alarm_2:
            messages.append(f"{prefix} Alarm Status 2: {alarm_2}")

        trip_1 = self.hub.get_raw_value(self.controller_id, "trip_status_1") or 0
        trip_2 = self.hub.get_raw_value(self.controller_id, "trip_status_2") or 0
        trip_3 = self.hub.get_raw_value(self.controller_id, "trip_status_3") or 0
        if trip_1 or trip_2 or trip_3:
            messages.append(f"{prefix} Trip aktiv")

        # Preserve order but remove duplicates.
        result: list[str] = []
        for message in messages:
            if message not in result:
                result.append(message)
        return result

    @property
    def extra_state_attributes(self):
        messages = self._alarm_messages()
        return {
            "controller": self.controller.name,
            "controller_slave": self.controller.slave,
            "active_alarm_count": len(messages),
            "active_alarms": messages,
            "alarm_status_1": self.hub.get_raw_value(self.controller_id, "alarm_status_1"),
            "alarm_status_2": self.hub.get_raw_value(self.controller_id, "alarm_status_2"),
            "trip_status_1": self.hub.get_raw_value(self.controller_id, "trip_status_1"),
            "arc_alarm_mask": self.hub.get_raw_value(self.controller_id, "arc_alarm_ch_1_8"),
        }


class FonrichGatewayAlarmTextSensor(SensorEntity):
    """Single compact alarm text sensor for the whole gateway."""

    _attr_has_entity_name = False

    def __init__(self, hub: FonrichHub) -> None:
        self.hub = hub
        self.entity_description = SensorEntityDescription(key="gateway_alarm_text")
        self._remove_callback = None
        self._attr_unique_id = f"{hub.gateway_uid}_gateway_alarm_text"
        self._attr_name = "Fonrich Alarmmeldung"

    async def async_added_to_hass(self) -> None:
        self._remove_callback = self.hub.callbacks.add(self.async_write_ha_state)

    async def async_will_remove_from_hass(self) -> None:
        if self._remove_callback:
            self._remove_callback()
            self._remove_callback = None

    @property
    def available(self) -> bool:
        return any(self.hub.available.values())

    @property
    def native_value(self):
        messages = self._all_messages()
        if not messages:
            return "OK"
        text = "; ".join(messages[:4])
        if len(messages) > 4:
            text += f"; +{len(messages) - 4} weitere"
        return text[:255]

    def _all_messages(self) -> list[str]:
        messages: list[str] = []
        for controller in self.hub.controllers:
            sensor = FonrichControllerAlarmTextSensor(self.hub, controller)
            messages.extend(sensor._alarm_messages())
        result: list[str] = []
        for message in messages:
            if message not in result:
                result.append(message)
        return result

    @property
    def extra_state_attributes(self):
        messages = self._all_messages()
        offline = [c.name for c in self.hub.controllers if not self.hub.available.get(c.controller_id, False)]
        return {
            "active_alarm_count": len(messages),
            "active_alarms": messages,
            "offline_controllers": offline,
        }
