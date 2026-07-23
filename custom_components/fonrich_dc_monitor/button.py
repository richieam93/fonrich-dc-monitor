from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_ENABLE_BUTTONS,
    CONF_ENABLE_SAFETY_TEST_BUTTONS,
    DEFAULT_ENABLE_BUTTONS,
    DEFAULT_ENABLE_SAFETY_TEST_BUTTONS,
)
from .coordinator import ControllerConfig, FonrichHub
from .entity import FonrichEntity
from .registers import BUTTONS, ButtonDescription


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    hub: FonrichHub = entry.runtime_data
    entities: list[ButtonEntity] = []

    if hub.options.get(CONF_ENABLE_BUTTONS, DEFAULT_ENABLE_BUTTONS):
        entities.extend(
            FonrichRegisterButton(hub, controller, description)
            for controller in hub.controllers
            for description in BUTTONS
        )

    if hub.options.get(CONF_ENABLE_SAFETY_TEST_BUTTONS, DEFAULT_ENABLE_SAFETY_TEST_BUTTONS):
        for controller in hub.controllers:
            entities.extend(
                [
                    FonrichArmRemoteTripButton(hub, controller),
                    FonrichRemoteTripButton(hub, controller),
                    FonrichLightningMessageTestButton(hub, controller),
                    FonrichClearTestMessagesButton(hub, controller),
                ]
            )

    async_add_entities(entities)


class FonrichRegisterButton(FonrichEntity, ButtonEntity):
    def __init__(self, hub: FonrichHub, controller: ControllerConfig, description: ButtonDescription) -> None:
        super().__init__(hub, controller, description.key)
        self.description = description
        self._attr_unique_id = f"{hub.gateway_uid}_{controller.controller_id}_{description.key}"
        self._attr_name = description.name
        self._attr_icon = description.icon

    @property
    def extra_state_attributes(self):
        return {
            **self.fonrich_attributes("command_button"),
            "action_key": self.description.key,
            "dangerous": self.description.key in {"clear_alarm_trip_status", "arc_selftest"},
        }

    async def async_press(self) -> None:
        await self.hub.write_register(self.controller, self.description.address, self.description.value)


class _FonrichSafetyButton(FonrichEntity, ButtonEntity):
    action_key: str

    @property
    def extra_state_attributes(self):
        return {
            **self.fonrich_attributes("safety_test_button"),
            "action_key": self.action_key,
            "dangerous": self.action_key == "remote_trip_test",
            "test_only": self.action_key in {"lightning_message_test", "clear_test_messages"},
            "remote_trip_armed": self.hub.remote_trip_is_armed(self.controller_id),
            "remote_trip_armed_until": self.hub.remote_trip_armed_until(self.controller_id),
        }


class FonrichArmRemoteTripButton(_FonrichSafetyButton):
    action_key = "arm_remote_trip_test"

    def __init__(self, hub: FonrichHub, controller: ControllerConfig) -> None:
        super().__init__(hub, controller, self.action_key)
        self._attr_unique_id = f"{hub.gateway_uid}_{controller.controller_id}_{self.action_key}"
        self._attr_name = "Hauptschalter-Test freigeben"
        self._attr_icon = "mdi:shield-key-outline"

    async def async_press(self) -> None:
        await self.hub.async_arm_remote_trip(self.controller)


class FonrichRemoteTripButton(_FonrichSafetyButton):
    action_key = "remote_trip_test"

    def __init__(self, hub: FonrichHub, controller: ControllerConfig) -> None:
        super().__init__(hub, controller, self.action_key)
        self._attr_unique_id = f"{hub.gateway_uid}_{controller.controller_id}_{self.action_key}"
        self._attr_name = "Hauptschalter-Schutz auslösen (Test)"
        self._attr_icon = "mdi:electric-switch-closed"

    async def async_press(self) -> None:
        await self.hub.async_remote_trip_test(self.controller)


class FonrichLightningMessageTestButton(_FonrichSafetyButton):
    action_key = "lightning_message_test"

    def __init__(self, hub: FonrichHub, controller: ControllerConfig) -> None:
        super().__init__(hub, controller, self.action_key)
        self._attr_unique_id = f"{hub.gateway_uid}_{controller.controller_id}_{self.action_key}"
        self._attr_name = "Blitzschutz-Meldetest (nur HA)"
        self._attr_icon = "mdi:weather-lightning"

    @property
    def available(self) -> bool:
        return True

    async def async_press(self) -> None:
        await self.hub.async_lightning_protection_message_test(self.controller)


class FonrichClearTestMessagesButton(_FonrichSafetyButton):
    action_key = "clear_test_messages"

    def __init__(self, hub: FonrichHub, controller: ControllerConfig) -> None:
        super().__init__(hub, controller, self.action_key)
        self._attr_unique_id = f"{hub.gateway_uid}_{controller.controller_id}_{self.action_key}"
        self._attr_name = "Testmeldungen zurücksetzen"
        self._attr_icon = "mdi:message-off-outline"

    @property
    def available(self) -> bool:
        return True

    async def async_press(self) -> None:
        await self.hub.async_clear_test_messages(self.controller)
