from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import (
    CONF_CONTROLLERS,
    CONF_HOST,
    CONF_PORT,
    CONF_RETRIES,
    CONF_TIMEOUT,
    DEFAULT_PORT,
    DEFAULT_RETRIES,
    DEFAULT_TIMEOUT,
    DOMAIN,
)
from .coordinator import ControllerConfig, FonrichHub
from .modbus_client import AsyncModbusTcpGateway

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR, Platform.BUTTON]

type FonrichConfigEntry = ConfigEntry[FonrichHub]

async def async_setup_entry(hass: HomeAssistant, entry: FonrichConfigEntry) -> bool:
    data = {**entry.data, **entry.options}
    host = data[CONF_HOST]
    port = int(data.get(CONF_PORT, DEFAULT_PORT))
    timeout = float(data.get(CONF_TIMEOUT, DEFAULT_TIMEOUT))
    retries = int(data.get(CONF_RETRIES, DEFAULT_RETRIES))

    controllers = []
    for item in data.get(CONF_CONTROLLERS, []):
        controllers.append(
            ControllerConfig(
                controller_id=item["id"],
                name=item["name"],
                slave=int(item["slave"]),
                enabled=bool(item.get("enabled", True)),
            )
        )

    client = AsyncModbusTcpGateway(host, port, timeout, retries)
    hub = FonrichHub(hass, client, controllers, entry.options)
    await hub.start()
    entry.runtime_data = hub

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    return True

async def async_unload_entry(hass: HomeAssistant, entry: FonrichConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok and entry.runtime_data:
        await entry.runtime_data.stop()
    return unload_ok

async def async_reload_entry(hass: HomeAssistant, entry: FonrichConfigEntry) -> None:
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)
