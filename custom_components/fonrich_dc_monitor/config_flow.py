from __future__ import annotations

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_NAME
from homeassistant.core import callback

from .const import (
    CONF_CONTROLLERS,
    CONF_ENABLE_ARC_INTENSITY,
    CONF_HOST,
    CONF_PORT,
    CONF_RETRIES,
    CONF_SCAN_ALARM,
    CONF_SCAN_ARC_INTENSITY,
    CONF_SCAN_BASE,
    CONF_SCAN_ENERGY,
    CONF_SCAN_POWER,
    CONF_TIMEOUT,
    DEFAULT_CONTROLLER_1,
    DEFAULT_CONTROLLER_2,
    DEFAULT_CONTROLLER_3,
    DEFAULT_HOST,
    DEFAULT_NAME,
    DEFAULT_PORT,
    DEFAULT_RETRIES,
    DEFAULT_SCAN_ALARM,
    DEFAULT_SCAN_ARC_INTENSITY,
    DEFAULT_SCAN_BASE,
    DEFAULT_SCAN_ENERGY,
    DEFAULT_SCAN_POWER,
    DEFAULT_TIMEOUT,
    DOMAIN,
)
from .modbus_client import AsyncModbusTcpGateway


def _controller_list_from_input(user_input: dict) -> list[dict]:
    controllers: list[dict] = []
    for idx, default_name in [(1, "V1 / Kasten 1"), (2, "V2 / Kasten 2"), (3, "V3 / Kasten 3")]:
        enabled = bool(user_input.get(f"controller_{idx}_enabled", True))
        slave = int(user_input.get(f"controller_{idx}_slave"))
        name = str(user_input.get(f"controller_{idx}_name", default_name))
        controllers.append({"id": f"v{idx}", "name": name, "slave": slave, "enabled": enabled})
    return controllers


def _default_controller_values(data: dict | None = None) -> dict:
    controllers = (data or {}).get(CONF_CONTROLLERS, [])
    by_id = {item.get("id"): item for item in controllers}
    defaults = {
        "controller_1_enabled": True,
        "controller_1_name": "V1 / Kasten 1",
        "controller_1_slave": DEFAULT_CONTROLLER_1,
        "controller_2_enabled": True,
        "controller_2_name": "V2 / Kasten 2",
        "controller_2_slave": DEFAULT_CONTROLLER_2,
        "controller_3_enabled": True,
        "controller_3_name": "V3 / Kasten 3",
        "controller_3_slave": DEFAULT_CONTROLLER_3,
    }
    for idx in range(1, 4):
        item = by_id.get(f"v{idx}")
        if item:
            defaults[f"controller_{idx}_enabled"] = bool(item.get("enabled", True))
            defaults[f"controller_{idx}_name"] = item.get("name", defaults[f"controller_{idx}_name"])
            defaults[f"controller_{idx}_slave"] = int(item.get("slave", defaults[f"controller_{idx}_slave"]))
    return defaults


def _connection_schema(defaults: dict | None = None) -> vol.Schema:
    defaults = defaults or {}
    return vol.Schema(
        {
            vol.Required(CONF_NAME, default=defaults.get(CONF_NAME, DEFAULT_NAME)): str,
            vol.Required(CONF_HOST, default=defaults.get(CONF_HOST, DEFAULT_HOST)): str,
            vol.Required(CONF_PORT, default=defaults.get(CONF_PORT, DEFAULT_PORT)): int,
            vol.Required(CONF_TIMEOUT, default=defaults.get(CONF_TIMEOUT, DEFAULT_TIMEOUT)): int,
            vol.Required(CONF_RETRIES, default=defaults.get(CONF_RETRIES, DEFAULT_RETRIES)): int,
        }
    )


def _controllers_schema(defaults: dict | None = None) -> vol.Schema:
    defaults = _default_controller_values(defaults)
    return vol.Schema(
        {
            vol.Required("controller_1_enabled", default=defaults["controller_1_enabled"]): bool,
            vol.Required("controller_1_name", default=defaults["controller_1_name"]): str,
            vol.Required("controller_1_slave", default=defaults["controller_1_slave"]): vol.All(int, vol.Range(min=1, max=247)),
            vol.Required("controller_2_enabled", default=defaults["controller_2_enabled"]): bool,
            vol.Required("controller_2_name", default=defaults["controller_2_name"]): str,
            vol.Required("controller_2_slave", default=defaults["controller_2_slave"]): vol.All(int, vol.Range(min=1, max=247)),
            vol.Required("controller_3_enabled", default=defaults["controller_3_enabled"]): bool,
            vol.Required("controller_3_name", default=defaults["controller_3_name"]): str,
            vol.Required("controller_3_slave", default=defaults["controller_3_slave"]): vol.All(int, vol.Range(min=1, max=247)),
        }
    )


def _options_schema(defaults: dict | None = None) -> vol.Schema:
    defaults = defaults or {}
    return vol.Schema(
        {
            vol.Required(CONF_SCAN_ALARM, default=defaults.get(CONF_SCAN_ALARM, DEFAULT_SCAN_ALARM)): vol.All(int, vol.Range(min=5, max=3600)),
            vol.Required(CONF_SCAN_BASE, default=defaults.get(CONF_SCAN_BASE, DEFAULT_SCAN_BASE)): vol.All(int, vol.Range(min=5, max=3600)),
            vol.Required(CONF_SCAN_POWER, default=defaults.get(CONF_SCAN_POWER, DEFAULT_SCAN_POWER)): vol.All(int, vol.Range(min=10, max=7200)),
            vol.Required(CONF_SCAN_ENERGY, default=defaults.get(CONF_SCAN_ENERGY, DEFAULT_SCAN_ENERGY)): vol.All(int, vol.Range(min=30, max=86400)),
            vol.Required(CONF_ENABLE_ARC_INTENSITY, default=defaults.get(CONF_ENABLE_ARC_INTENSITY, False)): bool,
            vol.Required(CONF_SCAN_ARC_INTENSITY, default=defaults.get(CONF_SCAN_ARC_INTENSITY, DEFAULT_SCAN_ARC_INTENSITY)): vol.All(int, vol.Range(min=10, max=7200)),
        }
    )

class FonrichConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._connection_data: dict = {}
        self._controller_data: dict = {}

    async def async_step_user(self, user_input: dict | None = None):
        errors: dict[str, str] = {}
        if user_input is not None:
            client = AsyncModbusTcpGateway(
                user_input[CONF_HOST], int(user_input[CONF_PORT]), float(user_input[CONF_TIMEOUT]), int(user_input[CONF_RETRIES])
            )
            try:
                # Connection smoke-test with default V1 address. Errors are not fatal because controller setup follows.
                await client.read_holding_registers(DEFAULT_CONTROLLER_1, 260, 1)
            except Exception:  # noqa: BLE001
                pass
            self._connection_data = dict(user_input)
            await self.async_set_unique_id(f"{user_input[CONF_HOST]}:{user_input[CONF_PORT]}")
            self._abort_if_unique_id_configured()
            return await self.async_step_controllers()

        return self.async_show_form(step_id="user", data_schema=_connection_schema(), errors=errors)

    async def async_step_controllers(self, user_input: dict | None = None):
        errors: dict[str, str] = {}
        if user_input is not None:
            self._controller_data = {CONF_CONTROLLERS: _controller_list_from_input(user_input)}
            return await self.async_step_options()
        return self.async_show_form(step_id="controllers", data_schema=_controllers_schema(), errors=errors)

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

    async def async_step_init(self, user_input: dict | None = None):
        return await self.async_step_connection()

    async def async_step_connection(self, user_input: dict | None = None):
        data = {**self.config_entry.data, **self.config_entry.options}
        if user_input is not None:
            self._connection_data = dict(user_input)
            return await self.async_step_controllers()
        defaults = {
            CONF_NAME: self.config_entry.title,
            CONF_HOST: data.get(CONF_HOST, DEFAULT_HOST),
            CONF_PORT: data.get(CONF_PORT, DEFAULT_PORT),
            CONF_TIMEOUT: data.get(CONF_TIMEOUT, DEFAULT_TIMEOUT),
            CONF_RETRIES: data.get(CONF_RETRIES, DEFAULT_RETRIES),
        }
        return self.async_show_form(step_id="connection", data_schema=_connection_schema(defaults))

    async def async_step_controllers(self, user_input: dict | None = None):
        data = {**self.config_entry.data, **self.config_entry.options}
        if user_input is not None:
            self._controller_data = {CONF_CONTROLLERS: _controller_list_from_input(user_input)}
            return await self.async_step_polling()
        return self.async_show_form(step_id="controllers", data_schema=_controllers_schema(data))

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
