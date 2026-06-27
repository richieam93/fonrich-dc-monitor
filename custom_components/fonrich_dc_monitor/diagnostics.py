from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .coordinator import FonrichHub
from .const import CONF_BAUDRATE, DEFAULT_BAUDRATE

async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: ConfigEntry) -> dict:
    hub: FonrichHub = entry.runtime_data
    return {
        "entry": {
            "title": entry.title,
            "data": dict(entry.data),
            "options": dict(entry.options),
        },
        "controllers": [
            {
                "id": controller.controller_id,
                "name": controller.name,
                "slave": controller.slave,
                "channel_count": controller.channel_count,
                "channel_descriptions": list(controller.channel_descriptions),
                "available": hub.available.get(controller.controller_id),
                "last_error": hub.last_error.get(controller.controller_id),
            }
            for controller in hub.controllers
        ],
        "scan_intervals": hub.scan_intervals,
        "configured_baudrate": {**entry.data, **entry.options}.get(CONF_BAUDRATE, DEFAULT_BAUDRATE),
    }
