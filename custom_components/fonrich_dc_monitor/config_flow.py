from __future__ import annotations

import asyncio
import re

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_NAME
from homeassistant.core import callback

from .const import (
    BAUDRATE_OPTIONS,
    CONF_BAUDRATE,
    CONF_CONTROLLERS,
    CONF_CONTROLLER_NAMES,
    CONF_CONTROLLER_SLAVES,
    CONF_ENABLE_ARC_INTENSITY,
    CONF_HOST,
    CONF_PORT,
    CONF_RETRIES,
    CONF_REQUIRE_ONLINE,
    CONF_SCAN_ALARM,
    CONF_SCAN_ARC_INTENSITY,
    CONF_SCAN_BASE,
    CONF_SCAN_ENERGY,
    CONF_SCAN_POWER,
    CONF_TIMEOUT,
    DEFAULT_BAUDRATE,
    DEFAULT_CONTROLLER_NAMES,
    DEFAULT_CONTROLLER_SLAVES,
    DEFAULT_HOST,
    DEFAULT_NAME,
    DEFAULT_PORT,
    DEFAULT_RETRIES,
    DEFAULT_REQUIRE_ONLINE,
    DEFAULT_SCAN_ALARM,
    DEFAULT_SCAN_ARC_INTENSITY,
    DEFAULT_SCAN_BASE,
    DEFAULT_SCAN_ENERGY,
    DEFAULT_SCAN_POWER,
    DEFAULT_TIMEOUT,
    CONF_SCAN_HISTORY,
    CONF_INTER_REQUEST_DELAY_MS,
    CONF_INTER_CONTROLLER_DELAY_MS,
    CONF_STARTUP_STAGGER_SECONDS,
    CONF_MAX_REGISTERS_PER_REQUEST,
    CONF_ENABLE_POWER,
    CONF_ENABLE_ENERGY,
    CONF_ENABLE_HISTORY,
    CONF_ENABLE_BUTTONS,
    CONF_ENABLE_ALARM_MASKS,
    DEFAULT_SCAN_HISTORY,
    DEFAULT_INTER_REQUEST_DELAY_MS,
    DEFAULT_INTER_CONTROLLER_DELAY_MS,
    DEFAULT_STARTUP_STAGGER_SECONDS,
    DEFAULT_MAX_REGISTERS_PER_REQUEST,
    DEFAULT_ENABLE_POWER,
    DEFAULT_ENABLE_ENERGY,
    DEFAULT_ENABLE_HISTORY,
    DEFAULT_ENABLE_BUTTONS,
    DEFAULT_ENABLE_ALARM_MASKS,
    DOMAIN,
)
from .modbus_client import AsyncModbusTcpGateway


def _split_csv(value: str) -> list[str]:
    return [part.strip() for part in re.split(r"[,;\n\r\t ]+", value or "") if part.strip()]


def _parse_slave_list(value: str) -> list[int]:
    slaves: list[int] = []
    seen: set[int] = set()
    for part in _split_csv(value):
        slave = int(part)
        if slave < 1 or slave > 247:
            raise ValueError("invalid_slave")
        if slave in seen:
            raise ValueError("duplicate_slave")
        seen.add(slave)
        slaves.append(slave)
    if not slaves:
        raise ValueError("no_slaves")
    return slaves


def _parse_names(value: str) -> list[str]:
    if not value:
        return []
    return [part.strip() for part in value.split(",") if part.strip()]


def _controller_list_from_text(slaves_text: str, names_text: str = "") -> list[dict]:
    slaves = _parse_slave_list(slaves_text)
    names = _parse_names(names_text)
    controllers: list[dict] = []
    for idx, slave in enumerate(slaves, start=1):
        default_name = f"V{idx} / Kasten {idx}"
        name = names[idx - 1] if idx <= len(names) else default_name
        controllers.append(
            {
                "id": f"slave_{slave}",
                "name": name,
                "slave": slave,
                "enabled": True,
            }
        )
    return controllers


def _controllers_to_text(data: dict | None = None) -> dict:
    controllers = (data or {}).get(CONF_CONTROLLERS, [])
    if controllers:
        return {
            CONF_CONTROLLER_SLAVES: ",".join(str(item.get("slave")) for item in controllers if item.get("enabled", True)),
            CONF_CONTROLLER_NAMES: ",".join(str(item.get("name", "")) for item in controllers if item.get("enabled", True)),
            CONF_REQUIRE_ONLINE: (data or {}).get(CONF_REQUIRE_ONLINE, DEFAULT_REQUIRE_ONLINE),
        }
    return {
        CONF_CONTROLLER_SLAVES: (data or {}).get(CONF_CONTROLLER_SLAVES, DEFAULT_CONTROLLER_SLAVES),
        CONF_CONTROLLER_NAMES: (data or {}).get(CONF_CONTROLLER_NAMES, DEFAULT_CONTROLLER_NAMES),
        CONF_REQUIRE_ONLINE: (data or {}).get(CONF_REQUIRE_ONLINE, DEFAULT_REQUIRE_ONLINE),
    }


async def _tcp_smoke_test(host: str, port: int, timeout: float) -> None:
    writer: asyncio.StreamWriter | None = None
    try:
        _reader, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout=timeout)
    finally:
        if writer is not None:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:  # noqa: BLE001
                pass


async def _test_controllers(host: str, port: int, timeout: float, retries: int, controllers: list[dict]) -> list[int]:
    client = AsyncModbusTcpGateway(host, port, timeout, retries)
    offline: list[int] = []
    for item in controllers:
        slave = int(item["slave"])
        try:
            await client.read_holding_registers(slave, 260, 1)
        except Exception:  # noqa: BLE001
            offline.append(slave)
    return offline


def _connection_schema(defaults: dict | None = None) -> vol.Schema:
    defaults = defaults or {}
    return vol.Schema(
        {
            vol.Required(CONF_NAME, default=defaults.get(CONF_NAME, DEFAULT_NAME)): str,
            vol.Required(CONF_HOST, default=defaults.get(CONF_HOST, DEFAULT_HOST)): str,
            vol.Required(CONF_PORT, default=defaults.get(CONF_PORT, DEFAULT_PORT)): vol.All(int, vol.Range(min=1, max=65535)),
            vol.Required(CONF_TIMEOUT, default=defaults.get(CONF_TIMEOUT, DEFAULT_TIMEOUT)): vol.All(int, vol.Range(min=1, max=60)),
            vol.Required(CONF_RETRIES, default=defaults.get(CONF_RETRIES, DEFAULT_RETRIES)): vol.All(int, vol.Range(min=0, max=10)),
            vol.Required(CONF_BAUDRATE, default=defaults.get(CONF_BAUDRATE, DEFAULT_BAUDRATE)): vol.In(BAUDRATE_OPTIONS),
        }
    )


def _controllers_schema(defaults: dict | None = None) -> vol.Schema:
    defaults = _controllers_to_text(defaults)
    return vol.Schema(
        {
            vol.Required(CONF_CONTROLLER_SLAVES, default=defaults[CONF_CONTROLLER_SLAVES]): str,
            vol.Optional(CONF_CONTROLLER_NAMES, default=defaults[CONF_CONTROLLER_NAMES]): str,
            vol.Required(CONF_REQUIRE_ONLINE, default=defaults[CONF_REQUIRE_ONLINE]): bool,
        }
    )


def _options_schema(defaults: dict | None = None) -> vol.Schema:
    defaults = defaults or {}
    return vol.Schema(
        {
            vol.Required(CONF_SCAN_ALARM, default=defaults.get(CONF_SCAN_ALARM, DEFAULT_SCAN_ALARM)): vol.All(int, vol.Range(min=5, max=3600)),
            vol.Required(CONF_SCAN_BASE, default=defaults.get(CONF_SCAN_BASE, DEFAULT_SCAN_BASE)): vol.All(int, vol.Range(min=5, max=3600)),
            vol.Required(CONF_ENABLE_POWER, default=defaults.get(CONF_ENABLE_POWER, DEFAULT_ENABLE_POWER)): bool,
            vol.Required(CONF_SCAN_POWER, default=defaults.get(CONF_SCAN_POWER, DEFAULT_SCAN_POWER)): vol.All(int, vol.Range(min=10, max=7200)),
            vol.Required(CONF_ENABLE_ENERGY, default=defaults.get(CONF_ENABLE_ENERGY, DEFAULT_ENABLE_ENERGY)): bool,
            vol.Required(CONF_SCAN_ENERGY, default=defaults.get(CONF_SCAN_ENERGY, DEFAULT_SCAN_ENERGY)): vol.All(int, vol.Range(min=30, max=86400)),
            vol.Required(CONF_ENABLE_HISTORY, default=defaults.get(CONF_ENABLE_HISTORY, DEFAULT_ENABLE_HISTORY)): bool,
            vol.Required(CONF_SCAN_HISTORY, default=defaults.get(CONF_SCAN_HISTORY, DEFAULT_SCAN_HISTORY)): vol.All(int, vol.Range(min=30, max=86400)),
            vol.Required(CONF_ENABLE_ARC_INTENSITY, default=defaults.get(CONF_ENABLE_ARC_INTENSITY, False)): bool,
            vol.Required(CONF_SCAN_ARC_INTENSITY, default=defaults.get(CONF_SCAN_ARC_INTENSITY, DEFAULT_SCAN_ARC_INTENSITY)): vol.All(int, vol.Range(min=10, max=7200)),
            vol.Required(CONF_ENABLE_ALARM_MASKS, default=defaults.get(CONF_ENABLE_ALARM_MASKS, DEFAULT_ENABLE_ALARM_MASKS)): bool,
            vol.Required(CONF_ENABLE_BUTTONS, default=defaults.get(CONF_ENABLE_BUTTONS, DEFAULT_ENABLE_BUTTONS)): bool,
            vol.Required(CONF_INTER_REQUEST_DELAY_MS, default=defaults.get(CONF_INTER_REQUEST_DELAY_MS, DEFAULT_INTER_REQUEST_DELAY_MS)): vol.All(int, vol.Range(min=0, max=5000)),
            vol.Required(CONF_INTER_CONTROLLER_DELAY_MS, default=defaults.get(CONF_INTER_CONTROLLER_DELAY_MS, DEFAULT_INTER_CONTROLLER_DELAY_MS)): vol.All(int, vol.Range(min=0, max=5000)),
            vol.Required(CONF_STARTUP_STAGGER_SECONDS, default=defaults.get(CONF_STARTUP_STAGGER_SECONDS, DEFAULT_STARTUP_STAGGER_SECONDS)): vol.All(int, vol.Range(min=0, max=120)),
            vol.Required(CONF_MAX_REGISTERS_PER_REQUEST, default=defaults.get(CONF_MAX_REGISTERS_PER_REQUEST, DEFAULT_MAX_REGISTERS_PER_REQUEST)): vol.All(int, vol.Range(min=1, max=60)),
        }
    )


class FonrichConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._connection_data: dict = {}
        self._controller_data: dict = {}
        self._last_offline: list[int] = []

    async def async_step_user(self, user_input: dict | None = None):
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                await _tcp_smoke_test(user_input[CONF_HOST], int(user_input[CONF_PORT]), float(user_input[CONF_TIMEOUT]))
            except Exception:  # noqa: BLE001
                errors["base"] = "cannot_connect"
            else:
                self._connection_data = dict(user_input)
                await self.async_set_unique_id(f"{user_input[CONF_HOST]}:{user_input[CONF_PORT]}")
                self._abort_if_unique_id_configured()
                return await self.async_step_controllers()

        return self.async_show_form(step_id="user", data_schema=_connection_schema(), errors=errors)

    async def async_step_controllers(self, user_input: dict | None = None):
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                controllers = _controller_list_from_text(
                    str(user_input.get(CONF_CONTROLLER_SLAVES, "")),
                    str(user_input.get(CONF_CONTROLLER_NAMES, "")),
                )
            except ValueError as exc:
                errors[CONF_CONTROLLER_SLAVES] = str(exc) or "invalid_slave"
            except Exception:  # noqa: BLE001
                errors[CONF_CONTROLLER_SLAVES] = "invalid_slave"
            else:
                require_online = bool(user_input.get(CONF_REQUIRE_ONLINE, DEFAULT_REQUIRE_ONLINE))
                if require_online:
                    offline = await _test_controllers(
                        self._connection_data[CONF_HOST],
                        int(self._connection_data[CONF_PORT]),
                        float(self._connection_data[CONF_TIMEOUT]),
                        int(self._connection_data[CONF_RETRIES]),
                        controllers,
                    )
                    if offline:
                        self._last_offline = offline
                        errors["base"] = "controllers_offline"
                    else:
                        self._controller_data = {
                            CONF_CONTROLLERS: controllers,
                            CONF_CONTROLLER_SLAVES: user_input.get(CONF_CONTROLLER_SLAVES, ""),
                            CONF_CONTROLLER_NAMES: user_input.get(CONF_CONTROLLER_NAMES, ""),
                            CONF_REQUIRE_ONLINE: require_online,
                        }
                        return await self.async_step_options()
                else:
                    self._controller_data = {
                        CONF_CONTROLLERS: controllers,
                        CONF_CONTROLLER_SLAVES: user_input.get(CONF_CONTROLLER_SLAVES, ""),
                        CONF_CONTROLLER_NAMES: user_input.get(CONF_CONTROLLER_NAMES, ""),
                        CONF_REQUIRE_ONLINE: require_online,
                    }
                    return await self.async_step_options()
        description_placeholders = {"offline": ", ".join(str(item) for item in self._last_offline)}
        return self.async_show_form(
            step_id="controllers",
            data_schema=_controllers_schema(),
            errors=errors,
            description_placeholders=description_placeholders,
        )

    async def async_step_options(self, user_input: dict | None = None):
        if user_input is not None:
            data = {**self._connection_data, **self._controller_data}
            title = str(data.pop(CONF_NAME, DEFAULT_NAME))
            return self.async_create_entry(title=title, data=data, options=dict(user_input))
        return self.async_show_form(step_id="options", data_schema=_options_schema())

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return FonrichOptionsFlow(config_entry)


class FonrichOptionsFlow(config_entries.OptionsFlow):
    def __init__(self, config_entry) -> None:
        self.config_entry = config_entry
        self._connection_data: dict = {}
        self._controller_data: dict = {}
        self._last_offline: list[int] = []

    async def async_step_init(self, user_input: dict | None = None):
        return await self.async_step_connection()

    async def async_step_connection(self, user_input: dict | None = None):
        data = {**self.config_entry.data, **self.config_entry.options}
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                await _tcp_smoke_test(user_input[CONF_HOST], int(user_input[CONF_PORT]), float(user_input[CONF_TIMEOUT]))
            except Exception:  # noqa: BLE001
                errors["base"] = "cannot_connect"
            else:
                self._connection_data = dict(user_input)
                return await self.async_step_controllers()
        defaults = {
            CONF_NAME: self.config_entry.title,
            CONF_HOST: data.get(CONF_HOST, DEFAULT_HOST),
            CONF_PORT: data.get(CONF_PORT, DEFAULT_PORT),
            CONF_TIMEOUT: data.get(CONF_TIMEOUT, DEFAULT_TIMEOUT),
            CONF_RETRIES: data.get(CONF_RETRIES, DEFAULT_RETRIES),
            CONF_BAUDRATE: data.get(CONF_BAUDRATE, DEFAULT_BAUDRATE),
        }
        return self.async_show_form(step_id="connection", data_schema=_connection_schema(defaults), errors=errors)

    async def async_step_controllers(self, user_input: dict | None = None):
        data = {**self.config_entry.data, **self.config_entry.options}
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                controllers = _controller_list_from_text(
                    str(user_input.get(CONF_CONTROLLER_SLAVES, "")),
                    str(user_input.get(CONF_CONTROLLER_NAMES, "")),
                )
            except ValueError as exc:
                errors[CONF_CONTROLLER_SLAVES] = str(exc) or "invalid_slave"
            except Exception:  # noqa: BLE001
                errors[CONF_CONTROLLER_SLAVES] = "invalid_slave"
            else:
                require_online = bool(user_input.get(CONF_REQUIRE_ONLINE, DEFAULT_REQUIRE_ONLINE))
                connection = self._connection_data or data
                if require_online:
                    offline = await _test_controllers(
                        connection[CONF_HOST],
                        int(connection[CONF_PORT]),
                        float(connection[CONF_TIMEOUT]),
                        int(connection[CONF_RETRIES]),
                        controllers,
                    )
                    if offline:
                        self._last_offline = offline
                        errors["base"] = "controllers_offline"
                    else:
                        self._controller_data = {
                            CONF_CONTROLLERS: controllers,
                            CONF_CONTROLLER_SLAVES: user_input.get(CONF_CONTROLLER_SLAVES, ""),
                            CONF_CONTROLLER_NAMES: user_input.get(CONF_CONTROLLER_NAMES, ""),
                            CONF_REQUIRE_ONLINE: require_online,
                        }
                        return await self.async_step_polling()
                else:
                    self._controller_data = {
                        CONF_CONTROLLERS: controllers,
                        CONF_CONTROLLER_SLAVES: user_input.get(CONF_CONTROLLER_SLAVES, ""),
                        CONF_CONTROLLER_NAMES: user_input.get(CONF_CONTROLLER_NAMES, ""),
                        CONF_REQUIRE_ONLINE: require_online,
                    }
                    return await self.async_step_polling()
        description_placeholders = {"offline": ", ".join(str(item) for item in self._last_offline)}
        return self.async_show_form(
            step_id="controllers",
            data_schema=_controllers_schema(data),
            errors=errors,
            description_placeholders=description_placeholders,
        )

    async def async_step_polling(self, user_input: dict | None = None):
        data = {**self.config_entry.data, **self.config_entry.options}
        if user_input is not None:
            new_options = {
                **self.config_entry.options,
                **self._connection_data,
                **self._controller_data,
                **dict(user_input),
            }
            return self.async_create_entry(title="", data=new_options)
        return self.async_show_form(step_id="polling", data_schema=_options_schema(data))
