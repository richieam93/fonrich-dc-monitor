from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .coordinator import FonrichHub
from .const import CONF_BAUDRATE, CONF_PROTOCOL, DEFAULT_BAUDRATE, DEFAULT_PROTOCOL

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
                "di_descriptions": list(controller.di_descriptions),
                "available": hub.available.get(controller.controller_id),
                "last_error": hub.last_error.get(controller.controller_id),
                "last_success": hub.last_success.get(controller.controller_id),
                "last_attempt": hub.last_attempt.get(controller.controller_id),
                "consecutive_errors": hub.consecutive_errors.get(controller.controller_id),
                "successful_polls": hub.successful_polls.get(controller.controller_id),
                "failed_polls": hub.failed_polls.get(controller.controller_id),
                "remote_trip_configuration": hub.remote_trip_configuration(controller.controller_id),
                "remote_trip_armed_until": hub.remote_trip_armed_until(controller.controller_id),
            }
            for controller in hub.controllers
        ],
        "scan_intervals": hub.scan_intervals,
        "configured_protocol": {**entry.data, **entry.options}.get(CONF_PROTOCOL, DEFAULT_PROTOCOL),
        "configured_baudrate": {**entry.data, **entry.options}.get(CONF_BAUDRATE, DEFAULT_BAUDRATE),
    }
