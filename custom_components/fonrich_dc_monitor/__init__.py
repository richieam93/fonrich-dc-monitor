from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall

from .const import (
    CONF_BAUDRATE,
    CONF_PROTOCOL,
    CONF_CONTROLLERS,
    CONF_HOST,
    CONF_PORT,
    CONF_RETRIES,
    CONF_TIMEOUT,
    DEFAULT_BAUDRATE,
    DEFAULT_PROTOCOL,
    DEFAULT_PORT,
    DEFAULT_RETRIES,
    DEFAULT_TIMEOUT,
    DEFAULT_CHANNEL_COUNT,
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


async def _async_register_frontend(hass: HomeAssistant, retry: int = 0) -> None:
    """Register Fonrich card static path and Lovelace resource automatically.

    The static URL is always registered. The Lovelace resource is added only in
    Lovelace storage mode. Newer Home Assistant versions lazy-load the resource
    storage, so we wait/retry until it is ready instead of creating too early.
    """
    from homeassistant.helpers.event import async_call_later

    www_path = Path(__file__).parent / "www"

    if not hass.data.get(f"{DOMAIN}_static_registered"):
        if www_path.exists() and hasattr(hass.http, "async_register_static_paths"):
            from homeassistant.components.http import StaticPathConfig
            try:
                await hass.http.async_register_static_paths([
                    StaticPathConfig(CARD_STATIC_URL, str(www_path), True)
                ])
                _LOGGER.debug("Registered Fonrich static card path: %s -> %s", CARD_STATIC_URL, www_path)
            except RuntimeError:
                _LOGGER.debug("Fonrich static card path already registered: %s", CARD_STATIC_URL)
            except Exception as err:  # noqa: BLE001
                _LOGGER.warning("Could not register Fonrich static card path %s: %s", CARD_STATIC_URL, err)
        elif www_path.exists():
            try:
                hass.http.register_static_path(CARD_STATIC_URL, str(www_path), True)
                _LOGGER.debug("Registered Fonrich static card path: %s -> %s", CARD_STATIC_URL, www_path)
            except RuntimeError:
                _LOGGER.debug("Fonrich static card path already registered: %s", CARD_STATIC_URL)
            except Exception as err:  # noqa: BLE001
                _LOGGER.warning("Could not register Fonrich static card path %s: %s", CARD_STATIC_URL, err)
        hass.data[f"{DOMAIN}_static_registered"] = True

    if hass.data.get(f"{DOMAIN}_lovelace_registered"):
        return

    lovelace = hass.data.get("lovelace")
    if lovelace is None:
        if retry < 24:
            _LOGGER.debug("Lovelace not ready, retry Fonrich card registration in 5s")
            async_call_later(hass, 5, lambda _now: hass.async_create_task(_async_register_frontend(hass, retry + 1)))
        else:
            _LOGGER.warning("Could not automatically register Fonrich Lovelace cards resource because Lovelace was not ready. The card file is available at %s", CARD_URL)
        return

    mode = getattr(lovelace, "mode", getattr(lovelace, "resource_mode", "storage"))
    if mode != "storage":
        _LOGGER.warning(
            "Fonrich card file is available at %s but Lovelace is not in storage mode. Automatic resource registration is only possible in storage mode.",
            CARD_URL,
        )
        return

    resources = getattr(lovelace, "resources", None)
    if resources is None:
        if retry < 24:
            _LOGGER.debug("Lovelace resources not ready, retry Fonrich card registration in 5s")
            async_call_later(hass, 5, lambda _now: hass.async_create_task(_async_register_frontend(hass, retry + 1)))
        else:
            _LOGGER.warning("Could not automatically register Fonrich Lovelace cards resource because resources were not ready. The card file is available at %s", CARD_URL)
        return

    # Avoid corrupting .storage/lovelace_resources on HA versions where resources
    # are lazy-loaded. Wait until loaded; if async_load exists, call it once.
    loaded = getattr(resources, "loaded", True)
    if loaded is False:
        try:
            if hasattr(resources, "async_load"):
                await resources.async_load()
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("Fonrich Lovelace resource async_load not ready: %s", err)
        loaded = getattr(resources, "loaded", True)
        if loaded is False:
            if retry < 24:
                _LOGGER.debug("Lovelace resources not loaded yet, retry Fonrich card registration in 5s")
                async_call_later(hass, 5, lambda _now: hass.async_create_task(_async_register_frontend(hass, retry + 1)))
            else:
                _LOGGER.warning("Could not automatically register Fonrich Lovelace cards resource because resources never loaded. The card file is available at %s", CARD_URL)
            return

    version = "0.0.0"
    try:
        import json
        manifest = json.loads((Path(__file__).parent / "manifest.json").read_text(encoding="utf-8"))
        version = str(manifest.get("version", version))
    except Exception:  # noqa: BLE001
        pass

    target_url = f"{CARD_URL}?v={version}"
    try:
        items = list(resources.async_items()) if hasattr(resources, "async_items") else []
        existing = [item for item in items if str(item.get("url", "")).split("?")[0] == CARD_URL]
        if existing:
            current = existing[0]
            if current.get("url") != target_url:
                await resources.async_update_item(current["id"], {"res_type": "module", "url": target_url})
                _LOGGER.info("Updated Fonrich Lovelace cards resource automatically: %s", target_url)
            else:
                _LOGGER.debug("Fonrich Lovelace cards resource already registered: %s", target_url)
            hass.data[f"{DOMAIN}_lovelace_registered"] = True
            return

        await resources.async_create_item({"res_type": "module", "url": target_url})
        _LOGGER.info("Registered Fonrich Lovelace cards resource automatically: %s", target_url)
        hass.data[f"{DOMAIN}_lovelace_registered"] = True
    except Exception as err:  # noqa: BLE001
        if retry < 6:
            _LOGGER.debug("Fonrich Lovelace resource registration failed, retry in 5s: %s", err)
            async_call_later(hass, 5, lambda _now: hass.async_create_task(_async_register_frontend(hass, retry + 1)))
        else:
            _LOGGER.warning(
                "Could not automatically register Fonrich Lovelace cards resource. The card file is available at %s. Error: %s",
                CARD_URL,
                err,
            )


async def _async_register_frontend_when_ready(hass: HomeAssistant) -> None:
    """Register frontend once Home Assistant has started."""
    from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
    from homeassistant.core import CoreState

    async def _setup_frontend(_event=None) -> None:
        await _async_register_frontend(hass)

    if hass.state == CoreState.running:
        await _setup_frontend()
    else:
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, _setup_frontend)

type FonrichConfigEntry = ConfigEntry[FonrichHub]

async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    await _async_register_frontend_when_ready(hass)
    return True

async def async_setup_entry(hass: HomeAssistant, entry: FonrichConfigEntry) -> bool:
    data = {**entry.data, **entry.options}
    host = data[CONF_HOST]
    port = int(data.get(CONF_PORT, DEFAULT_PORT))
    timeout = float(data.get(CONF_TIMEOUT, DEFAULT_TIMEOUT))
    retries = int(data.get(CONF_RETRIES, DEFAULT_RETRIES))
    baudrate = int(data.get(CONF_BAUDRATE, DEFAULT_BAUDRATE))
    protocol = str(data.get(CONF_PROTOCOL, DEFAULT_PROTOCOL))
    _LOGGER.debug("Fonrich gateway protocol=%s baudrate=%s. Set the HF2211 and controllers accordingly.", protocol, baudrate)

    controllers = []
    for item in data.get(CONF_CONTROLLERS, []):
        controllers.append(
            ControllerConfig(
                controller_id=item["id"],
                name=item["name"],
                slave=int(item["slave"]),
                enabled=bool(item.get("enabled", True)),
                channel_count=int(item.get("channel_count", DEFAULT_CHANNEL_COUNT)),
                channel_descriptions=tuple(item.get("channel_descriptions", [])),
            )
        )

    client = AsyncModbusTcpGateway(host, port, timeout, retries, protocol)
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
