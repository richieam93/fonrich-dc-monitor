from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall

from .const import (
    CONF_BAUDRATE,
    CONF_CONTROLLERS,
    CONF_HOST,
    CONF_PORT,
    CONF_RETRIES,
    CONF_TIMEOUT,
    DEFAULT_BAUDRATE,
    DEFAULT_PORT,
    DEFAULT_RETRIES,
    DEFAULT_TIMEOUT,
    DOMAIN,
)
from .coordinator import ControllerConfig, FonrichHub
from .modbus_client import AsyncModbusTcpGateway

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR, Platform.BUTTON]

CARD_URL = "/fonrich_dc_monitor/fonrich-dc-monitor-cards.js"
CARD_STATIC_URL = "/fonrich_dc_monitor"
CARD_FILE = "fonrich-dc-monitor-cards.js"

SERVICE_REFRESH_NOW = "refresh_now"
SERVICE_CLEAR_ALARM_TRIP = "clear_alarm_trip"
SERVICE_CLEAR_ARC_HISTORY = "clear_arc_history"
SERVICE_ARC_SELFTEST = "arc_selftest"

def _hubs(hass: HomeAssistant) -> list[FonrichHub]:
    return [entry.runtime_data for entry in hass.config_entries.async_entries(DOMAIN) if getattr(entry, "runtime_data", None)]

async def _handle_refresh_now(hass: HomeAssistant, call: ServiceCall) -> None:
    for hub in _hubs(hass):
        await hub.async_refresh_all()

async def _handle_controller_service(hass: HomeAssistant, call: ServiceCall, action: str) -> None:
    controller_value = call.data.get("controller")
    for hub in _hubs(hass):
        controller = hub.controller_by_id_or_slave(controller_value)
        if controller is None:
            continue
        if action == SERVICE_CLEAR_ALARM_TRIP:
            await hub.async_clear_alarm_trip(controller)
        elif action == SERVICE_CLEAR_ARC_HISTORY:
            await hub.async_clear_arc_history(controller)
        elif action == SERVICE_ARC_SELFTEST:
            await hub.async_arc_selftest(controller)
        return
    raise ValueError(f"Fonrich controller not found: {controller_value}")


async def _async_register_frontend(hass: HomeAssistant) -> None:
    """Register Fonrich Lovelace cards and static www path."""
    www_path = Path(__file__).parent / "www"
    if www_path.exists() and hasattr(hass.http, "async_register_static_paths"):
        from homeassistant.components.http import StaticPathConfig
        try:
            await hass.http.async_register_static_paths([
                StaticPathConfig(CARD_STATIC_URL, str(www_path), True)
            ])
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("Fonrich static card path already registered or failed: %s", err)
    elif www_path.exists():
        try:
            hass.http.register_static_path(CARD_STATIC_URL, str(www_path), True)
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("Fonrich static card path already registered or failed: %s", err)

    # Best effort: add Lovelace resource automatically so cards appear in the visual editor.
    # The resource API has changed between HA releases, therefore we try the supported
    # helper first and fall back silently to a repair/persistent notification style log.
    try:
        from homeassistant.components.lovelace.resources import async_get_resource_collection

        resources = await async_get_resource_collection(hass)
        items = await resources.async_load()
        for item in items:
            if item.get("url") == CARD_URL or item.get("url", "").startswith(CARD_URL + "?"):
                return

        # HA resource storage expects res_type in recent releases.
        try:
            await resources.async_create_item({"res_type": "module", "url": CARD_URL})
        except Exception:
            # Older/custom builds may expect type instead of res_type.
            await resources.async_create_item({"type": "module", "url": CARD_URL})
        _LOGGER.info("Fonrich Lovelace cards resource registered automatically: %s", CARD_URL)
    except Exception as err:  # noqa: BLE001
        _LOGGER.warning(
            "Could not automatically register Fonrich Lovelace cards resource. "
            "Add %s as JavaScript module manually if the cards do not appear. Error: %s",
            CARD_URL,
            err,
        )

type FonrichConfigEntry = ConfigEntry[FonrichHub]

async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    await _async_register_frontend(hass)
    return True

async def async_setup_entry(hass: HomeAssistant, entry: FonrichConfigEntry) -> bool:
    data = {**entry.data, **entry.options}
    host = data[CONF_HOST]
    port = int(data.get(CONF_PORT, DEFAULT_PORT))
    timeout = float(data.get(CONF_TIMEOUT, DEFAULT_TIMEOUT))
    retries = int(data.get(CONF_RETRIES, DEFAULT_RETRIES))
    baudrate = int(data.get(CONF_BAUDRATE, DEFAULT_BAUDRATE))
    _LOGGER.debug("Fonrich gateway serial baudrate setting is %s baud. This is informational; set the HF2211 and controllers to the same baudrate.", baudrate)

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
    hub = FonrichHub(hass, client, controllers, entry.options, gateway_uid=entry.entry_id)
    await hub.start()
    entry.runtime_data = hub

    await _async_register_frontend(hass)

    if not hass.services.has_service(DOMAIN, SERVICE_REFRESH_NOW):
        async def _service_refresh(call: ServiceCall) -> None:
            await _handle_refresh_now(hass, call)

        async def _service_clear_alarm_trip(call: ServiceCall) -> None:
            await _handle_controller_service(hass, call, SERVICE_CLEAR_ALARM_TRIP)

        async def _service_clear_arc_history(call: ServiceCall) -> None:
            await _handle_controller_service(hass, call, SERVICE_CLEAR_ARC_HISTORY)

        async def _service_arc_selftest(call: ServiceCall) -> None:
            await _handle_controller_service(hass, call, SERVICE_ARC_SELFTEST)

        hass.services.async_register(DOMAIN, SERVICE_REFRESH_NOW, _service_refresh)
        hass.services.async_register(DOMAIN, SERVICE_CLEAR_ALARM_TRIP, _service_clear_alarm_trip)
        hass.services.async_register(DOMAIN, SERVICE_CLEAR_ARC_HISTORY, _service_clear_arc_history)
        hass.services.async_register(DOMAIN, SERVICE_ARC_SELFTEST, _service_arc_selftest)

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
