from __future__ import annotations

import re

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfElectricCurrent, UnitOfElectricPotential, UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_ENABLE_ALARM_MASKS,
    CONF_ENABLE_ALARM_TEXT_SENSOR,
    CONF_ENABLE_ARC_INTENSITY,
    CONF_ENABLE_CHANNEL_VOLTAGE,
    CONF_ENABLE_DAILY_MAX_CURRENT,
    CONF_ENABLE_ENERGY,
    CONF_ENABLE_HISTORY,
    CONF_ENABLE_POWER,
    CONF_SENSOR_PROFILE,
    DEFAULT_ENABLE_ALARM_MASKS,
    DEFAULT_ENABLE_ALARM_TEXT_SENSOR,
    DEFAULT_ENABLE_CHANNEL_VOLTAGE,
    DEFAULT_ENABLE_DAILY_MAX_CURRENT,
    DEFAULT_ENABLE_ENERGY,
    DEFAULT_ENABLE_HISTORY,
    DEFAULT_ENABLE_POWER,
    DEFAULT_SENSOR_PROFILE,
    SENSOR_PROFILE_DIAGNOSTIC,
    SENSOR_PROFILE_PRODUCTION,
    SENSOR_PROFILE_STANDARD,
)
from .coordinator import ControllerConfig, FonrichHub
from .entity import FonrichEntity
from .registers import ALL_SENSOR_REGISTERS, RegisterDescription

_CHANNEL_RE = re.compile(r"^ch(\d+)_")


def _channel_from_key(key: str) -> int | None:
    match = _CHANNEL_RE.match(key)
    return int(match.group(1)) if match else None


def _is_enabled_for_controller(controller: ControllerConfig, key: str) -> bool:
    channel = _channel_from_key(key)
    return channel is None or channel <= int(controller.channel_count)


def _production_register(description: RegisterDescription) -> bool:
    if description.key in {"voltage", "total_current", "total_power_direct"}:
        return True
    if re.fullmatch(r"ch\d+_current", description.key):
        return True
    if re.fullmatch(r"ch\d+_power_direct", description.key):
        return True
    return False


def _sensor_enabled(hub: FonrichHub, description: RegisterDescription) -> bool:
    profile = str(hub.options.get(CONF_SENSOR_PROFILE, DEFAULT_SENSOR_PROFILE))

    if profile == SENSOR_PROFILE_PRODUCTION:
        if not _production_register(description):
            return False
    elif profile == SENSOR_PROFILE_STANDARD:
        if description.category in {"diagnostic", "arc_intensity"}:
            return False
    elif profile != SENSOR_PROFILE_DIAGNOSTIC and description.category in {"diagnostic", "arc_intensity"}:
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
    (1, "Bus-Lichtbogen"),
    (2, "Kanal-Lichtbogen"),
    (4, "Unterspannung"),
    (8, "Überspannung"),
    (16, "Temperatur 1 zu hoch"),
    (32, "Temperatur 2 zu hoch"),
    (64, "Kanal-Rückstrom"),
    (128, "Gesamt-Rückstrom zu hoch"),
    (256, "Gesamtstrom zu niedrig"),
    (512, "Gesamtstrom zu hoch"),
    (1024, "Kanal ohne Strom"),
    (2048, "Kanal-Unterstrom"),
    (4096, "Kanal-Überstrom"),
    (8192, "Kanalstrom zu niedrig"),
    (16384, "Kanalstrom zu hoch"),
]

CHANNEL_MASKS = [
    ("arc_alarm_ch_1_8", "Lichtbogen"),
    ("reverse_current_alarm_mask", "Rückstrom"),
    ("no_current_alarm_mask", "Kein Strom"),
    ("undercurrent_alarm_mask", "Unterstrom"),
    ("overcurrent_alarm_mask", "Überstrom"),
    ("current_low_alarm_mask", "Strom zu niedrig"),
    ("current_high_alarm_mask", "Strom zu hoch"),
    ("arc_selfcheck_fail_mask", "Lichtbogen-Selbsttestfehler"),
]


def _alarm_text_enabled(hub: FonrichHub) -> bool:
    return bool(hub.options.get(CONF_ENABLE_ALARM_TEXT_SENSOR, DEFAULT_ENABLE_ALARM_TEXT_SENSOR))


def _channel_name(controller: ControllerConfig, channel: int) -> str:
    description = controller.channel_description(channel).strip()
    base = f"Kanal {channel:02d}"
    if description and description.lower() not in {f"kanal {channel}", f"kanal {channel:02d}"}:
        return f"{base} ({description})"
    return base


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    hub: FonrichHub = entry.runtime_data
    entities: list[SensorEntity] = []

    if _alarm_text_enabled(hub):
        entities.append(FonrichGatewayAlarmTextSensor(hub))
        entities.extend(FonrichControllerAlarmTextSensor(hub, controller) for controller in hub.controllers)

    for controller in hub.controllers:
        for description in ALL_SENSOR_REGISTERS:
            if not _is_enabled_for_controller(controller, description.key):
                continue
            if not _sensor_enabled(hub, description):
                continue
            entities.append(FonrichSensor(hub, controller, description))

        if hub.options.get(CONF_ENABLE_CHANNEL_VOLTAGE, DEFAULT_ENABLE_CHANNEL_VOLTAGE):
            entities.extend(
                FonrichChannelVoltageSensor(hub, controller, channel)
                for channel in range(1, controller.channel_count + 1)
            )

        if hub.options.get(CONF_ENABLE_DAILY_MAX_CURRENT, DEFAULT_ENABLE_DAILY_MAX_CURRENT):
            entities.extend(
                FonrichDailyMaxCurrentSensor(hub, controller, channel)
                for channel in range(1, controller.channel_count + 1)
            )

    async_add_entities(entities)


class FonrichSensor(FonrichEntity, SensorEntity):
    def __init__(self, hub: FonrichHub, controller: ControllerConfig, description: RegisterDescription) -> None:
        super().__init__(hub, controller, description.key)
        self.description = description
        self.channel = _channel_from_key(description.key)
        self.entity_description = SensorEntityDescription(
            key=description.key,
            device_class=description.device_class,
            state_class=description.state_class,
            native_unit_of_measurement=description.unit,
            suggested_display_precision=description.precision,
        )
        self._attr_unique_id = f"{hub.gateway_uid}_{controller.controller_id}_{description.key}"
        self._attr_name = self._friendly_name(description)
        self._attr_native_unit_of_measurement = description.unit
        self._attr_device_class = description.device_class
        self._attr_state_class = description.state_class
        self._attr_suggested_display_precision = description.precision

    def _friendly_name(self, description: RegisterDescription) -> str:
        if description.key == "voltage":
            return "Spannung"
        if description.key == "total_current":
            return "Gesamtstrom"
        if description.key == "total_power_direct":
            return "Gesamtleistung"
        if self.channel is not None:
            prefix = _channel_name(self.controller, self.channel)
            if description.key.endswith("_current"):
                return f"{prefix} Ampere"
            if description.key.endswith("_power_direct"):
                return f"{prefix} Leistung"
            suffix = re.sub(rf"^Kanal\s+{self.channel}\s*", "", description.name).strip()
            return f"{prefix} {suffix}".strip()
        return description.name

    @property
    def native_value(self):
        return self.hub.get_value(self.controller_id, self.key)

    @property
    def extra_state_attributes(self):
        if self.channel is None:
            return {"controller_slave": self.controller.slave}
        return {
            "channel": self.channel,
            "channel_description": self.controller.channel_description(self.channel),
            "controller_slave": self.controller.slave,
        }


class FonrichChannelVoltageSensor(FonrichEntity, SensorEntity):
    """Expose the controller bus voltage under every channel for a clear UI layout."""

    def __init__(self, hub: FonrichHub, controller: ControllerConfig, channel: int) -> None:
        super().__init__(hub, controller, f"ch{channel}_voltage")
        self.channel = channel
        self.entity_description = SensorEntityDescription(
            key=f"ch{channel}_voltage",
            device_class=SensorDeviceClass.VOLTAGE,
            state_class=SensorStateClass.MEASUREMENT,
            native_unit_of_measurement=UnitOfElectricPotential.VOLT,
            suggested_display_precision=0,
        )
        self._attr_unique_id = f"{hub.gateway_uid}_{controller.controller_id}_ch{channel}_voltage"
        self._attr_name = f"{_channel_name(controller, channel)} Spannung"

    @property
    def native_value(self):
        return self.hub.get_value(self.controller_id, "voltage")

    @property
    def extra_state_attributes(self):
        return {
            "channel": self.channel,
            "channel_description": self.controller.channel_description(self.channel),
            "controller_slave": self.controller.slave,
            "source": "controller_bus_voltage",
            "note": "Der Fonrich liefert eine gemeinsame Busspannung pro Kasten; dieser Wert wird dem Kanal zugeordnet.",
        }


class FonrichDailyMaxCurrentSensor(FonrichEntity, SensorEntity):
    """Highest measured channel current since local midnight."""

    def __init__(self, hub: FonrichHub, controller: ControllerConfig, channel: int) -> None:
        super().__init__(hub, controller, f"ch{channel}_daily_max_current")
        self.channel = channel
        self.entity_description = SensorEntityDescription(
            key=f"ch{channel}_daily_max_current",
            device_class=SensorDeviceClass.CURRENT,
            state_class=SensorStateClass.MEASUREMENT,
            native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
            suggested_display_precision=3,
        )
        self._attr_unique_id = f"{hub.gateway_uid}_{controller.controller_id}_ch{channel}_daily_max_current"
        self._attr_name = f"{_channel_name(controller, channel)} Max. Ampere heute"

    @property
    def available(self) -> bool:
        return self.hub.get_daily_max_current(self.controller_id, self.channel) is not None

    @property
    def native_value(self):
        return self.hub.get_daily_max_current(self.controller_id, self.channel)

    @property
    def extra_state_attributes(self):
        return {
            "channel": self.channel,
            "channel_description": self.controller.channel_description(self.channel),
            "controller_slave": self.controller.slave,
            "period": "today",
        }


class FonrichControllerAlarmTextSensor(FonrichEntity, SensorEntity):
    """One readable message sensor per controller."""

    def __init__(self, hub: FonrichHub, controller: ControllerConfig) -> None:
        super().__init__(hub, controller, "alarm_text")
        self.entity_description = SensorEntityDescription(key="alarm_text")
        self._attr_unique_id = f"{hub.gateway_uid}_{controller.controller_id}_alarm_text"
        self._attr_name = "Meldungen"
        self._attr_icon = "mdi:message-alert-outline"

    @property
    def available(self) -> bool:
        return True

    @property
    def native_value(self):
        messages = self.alarm_messages()
        if not self.hub.available.get(self.controller_id, False):
            return f"{self.controller.display_name} offline"
        return "OK" if not messages else "; ".join(messages)[:255]

    def alarm_messages(self) -> list[str]:
        messages: list[str] = []
        controller_name = self.controller.display_name

        for key, label in CHANNEL_MASKS:
            raw = self.hub.get_raw_value(self.controller_id, key) or 0
            for channel in range(1, min(int(self.controller.channel_count), 16) + 1):
                if raw & (1 << (channel - 1)):
                    text = f"{label} bei {controller_name}, Kanal {channel:02d}"
                    description = self.controller.channel_description(channel).strip()
                    if description and description.lower() not in {f"kanal {channel}", f"kanal {channel:02d}"}:
                        text += f" ({description})"
                    messages.append(text)

        alarm_1 = self.hub.get_raw_value(self.controller_id, "alarm_status_1") or 0
        exact_labels = {message.split(" bei ", 1)[0] for message in messages}
        for bit, label in ALARM_STATUS_1_BITS:
            if not alarm_1 & bit:
                continue
            if label == "Kanal-Lichtbogen" and "Lichtbogen" in exact_labels:
                continue
            if label in {"Kanal-Rückstrom", "Kanal ohne Strom", "Kanal-Unterstrom", "Kanal-Überstrom", "Kanalstrom zu niedrig", "Kanalstrom zu hoch"}:
                normalized = label.replace("Kanal-", "").replace("Kanal", "").strip()
                if any(normalized.lower() in item.lower() for item in messages):
                    continue
            messages.append(f"{label} bei {controller_name}")

        alarm_2 = self.hub.get_raw_value(self.controller_id, "alarm_status_2") or 0
        if alarm_2:
            messages.append(f"Weitere Alarmmeldung bei {controller_name} (Code {alarm_2})")

        trip_values = [self.hub.get_raw_value(self.controller_id, f"trip_status_{index}") or 0 for index in range(1, 4)]
        if any(trip_values):
            messages.append(f"Trip aktiv bei {controller_name}")

        result: list[str] = []
        for message in messages:
            if message not in result:
                result.append(message)
        return result

    @property
    def extra_state_attributes(self):
        messages = self.alarm_messages()
        return {
            "controller": self.controller.display_name,
            "controller_slave": self.controller.slave,
            "online": self.hub.available.get(self.controller_id, False),
            "active_message_count": len(messages),
            "active_messages": messages,
            "last_error": self.hub.last_error.get(self.controller_id),
        }


class FonrichGatewayAlarmTextSensor(SensorEntity):
    """Single combined message sensor for every controller on the gateway."""

    _attr_has_entity_name = False

    def __init__(self, hub: FonrichHub) -> None:
        self.hub = hub
        self.entity_description = SensorEntityDescription(key="gateway_alarm_text")
        self._remove_callback = None
        self._attr_unique_id = f"{hub.gateway_uid}_gateway_alarm_text"
        self._attr_name = "Fonrich Meldungen"
        self._attr_icon = "mdi:message-alert"

    async def async_added_to_hass(self) -> None:
        self._remove_callback = self.hub.callbacks.add(self.async_write_ha_state)

    async def async_will_remove_from_hass(self) -> None:
        if self._remove_callback:
            self._remove_callback()
            self._remove_callback = None

    @property
    def available(self) -> bool:
        return True

    @property
    def native_value(self):
        messages = self.all_messages()
        return "OK" if not messages else "; ".join(messages)[:255]

    def all_messages(self) -> list[str]:
        messages: list[str] = []
        for controller in self.hub.controllers:
            if not self.hub.available.get(controller.controller_id, False):
                messages.append(f"{controller.display_name} offline")
                continue
            messages.extend(FonrichControllerAlarmTextSensor(self.hub, controller).alarm_messages())
        result: list[str] = []
        for message in messages:
            if message not in result:
                result.append(message)
        return result

    @property
    def extra_state_attributes(self):
        messages = self.all_messages()
        return {
            "active_message_count": len(messages),
            "active_messages": messages,
            "online_controllers": [
                controller.display_name
                for controller in self.hub.controllers
                if self.hub.available.get(controller.controller_id, False)
            ],
            "offline_controllers": [
                controller.display_name
                for controller in self.hub.controllers
                if not self.hub.available.get(controller.controller_id, False)
            ],
        }
