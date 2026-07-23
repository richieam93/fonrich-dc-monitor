from __future__ import annotations

from homeassistant.helpers.entity import DeviceInfo, Entity

from .const import DOMAIN
from .coordinator import ControllerConfig, FonrichHub


class FonrichEntity(Entity):
    _attr_has_entity_name = True

    def __init__(self, hub: FonrichHub, controller: ControllerConfig, key: str) -> None:
        self.hub = hub
        self.controller = controller
        self.controller_id = controller.controller_id
        self.key = key
        self._remove_callback = None
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{hub.gateway_uid}_{controller.controller_id}")},
            name=controller.display_name,
            manufacturer="Fonrich",
            model="FR-DCMG-MMPS",
            configuration_url=f"http://{hub.client.host}",
        )

    async def async_added_to_hass(self) -> None:
        self._remove_callback = self.hub.callbacks.add(self.async_write_ha_state)

    async def async_will_remove_from_hass(self) -> None:
        if self._remove_callback:
            self._remove_callback()
            self._remove_callback = None

    @property
    def available(self) -> bool:
        return self.hub.available.get(self.controller_id, False)

    def fonrich_attributes(self, role: str | None = None) -> dict:
        """Stable metadata used by the bundled Lovelace cards.

        Cards should not depend on translated friendly names. These attributes
        are deliberately language independent and remain stable across renames.
        """
        data = {
            "fonrich_integration": True,
            "fonrich_key": self.key,
            "controller": self.controller.display_name,
            "controller_id": self.controller.controller_id,
            "controller_slave": self.controller.slave,
        }
        if role:
            data["fonrich_role"] = role
        return data
