from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import (
    CONF_ENABLE_ALARM_BINARY_SENSORS,
    CONF_ENABLE_ALARM_MASKS,
    CONF_ENABLE_ALARM_TEXT_SENSOR,
    CONF_ENABLE_ARC_INTENSITY,
    CONF_ENABLE_ENERGY,
    CONF_ENABLE_HISTORY,
    CONF_ENABLE_POWER,
    CONF_INTER_CONTROLLER_DELAY_MS,
    CONF_INTER_REQUEST_DELAY_MS,
    CONF_MAX_REGISTERS_PER_REQUEST,
    CONF_SCAN_ALARM,
    CONF_SCAN_ARC_INTENSITY,
    CONF_SCAN_BASE,
    CONF_SCAN_ENERGY,
    CONF_SCAN_HISTORY,
    CONF_SCAN_POWER,
    CONF_SENSOR_PROFILE,
    CONF_STARTUP_STAGGER_SECONDS,
    DEFAULT_ENABLE_ALARM_BINARY_SENSORS,
    DEFAULT_ENABLE_ALARM_MASKS,
    DEFAULT_ENABLE_ALARM_TEXT_SENSOR,
    DEFAULT_ENABLE_ENERGY,
    DEFAULT_ENABLE_HISTORY,
    DEFAULT_ENABLE_POWER,
    DEFAULT_INTER_CONTROLLER_DELAY_MS,
    DEFAULT_INTER_REQUEST_DELAY_MS,
    DEFAULT_MAX_REGISTERS_PER_REQUEST,
    DEFAULT_SCAN_ALARM,
    DEFAULT_SCAN_ARC_INTENSITY,
    DEFAULT_SCAN_BASE,
    DEFAULT_SCAN_ENERGY,
    DEFAULT_SCAN_HISTORY,
    DEFAULT_SCAN_POWER,
    DEFAULT_SENSOR_PROFILE,
    DEFAULT_STARTUP_STAGGER_SECONDS,
    DOMAIN,
    SENSOR_PROFILE_DIAGNOSTIC,
    SENSOR_PROFILE_PRODUCTION,
    SENSOR_PROFILE_STANDARD,
)
from .modbus_client import AsyncModbusTcpGateway, CallbackRegistry
from .registers import ALL_SENSOR_REGISTERS, RegisterDescription

_LOGGER = logging.getLogger(__name__)
_CHANNEL_RE = re.compile(r"^ch(\d+)_")
_VERSION = 1


def _channel_from_key(key: str) -> int | None:
    match = _CHANNEL_RE.match(key)
    return int(match.group(1)) if match else None


@dataclass(frozen=True)
class ControllerConfig:
    controller_id: str
    name: str
    slave: int
    enabled: bool = True
    channel_count: int = 8
    channel_descriptions: tuple[str, ...] = ()

    @property
    def display_name(self) -> str:
        """Return a consistent controller name while preserving custom names."""
        name = str(self.name).strip()
        match = re.search(r"\bV\s*(\d+)\b", name, re.IGNORECASE)
        if match:
            return f"Kasten V{match.group(1)}"
        if re.fullmatch(r"Kasten\s+\d+", name, re.IGNORECASE):
            number = re.search(r"\d+", name)
            return f"Kasten V{number.group(0)}" if number else name
        return name or f"Kasten Slave {self.slave}"

    def channel_description(self, channel: int) -> str:
        if channel < 1 or channel > self.channel_count:
            return ""
        index = channel - 1
        if index < len(self.channel_descriptions):
            return self.channel_descriptions[index]
        return ""


class FonrichHub:
    """Shared data hub that serializes and staggers Modbus polling."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: AsyncModbusTcpGateway,
        controllers: list[ControllerConfig],
        options: dict,
        gateway_uid: str = "fonrich",
    ) -> None:
        self.hass = hass
        self.gateway_uid = gateway_uid
        self.client = client
        self.controllers = [controller for controller in controllers if controller.enabled]
        self.options = options
        self.data: dict[str, dict[str, int | float | None]] = {c.controller_id: {} for c in self.controllers}
        self.raw: dict[str, dict[str, int | None]] = {c.controller_id: {} for c in self.controllers}
        self.available: dict[str, bool] = {c.controller_id: False for c in self.controllers}
        self.last_error: dict[str, str | None] = {c.controller_id: None for c in self.controllers}
        self.callbacks = CallbackRegistry()
        self._tasks: list[asyncio.Task] = []
        self._stopped = asyncio.Event()
        self._daily_max_store: Store[dict[str, Any]] = Store(
            hass,
            _VERSION,
            f"{DOMAIN}.{gateway_uid}.daily_max_current",
        )
        self._daily_max_date = dt_util.now().date().isoformat()
        self.daily_max_current: dict[str, dict[int, float]] = {
            c.controller_id: {channel: 0.0 for channel in range(1, c.channel_count + 1)}
            for c in self.controllers
        }

    @property
    def sensor_profile(self) -> str:
        return str(self.options.get(CONF_SENSOR_PROFILE, DEFAULT_SENSOR_PROFILE))

    @property
    def scan_intervals(self) -> dict[str, int]:
        return {
            "alarm": int(self.options.get(CONF_SCAN_ALARM, DEFAULT_SCAN_ALARM)),
            "base": int(self.options.get(CONF_SCAN_BASE, DEFAULT_SCAN_BASE)),
            "power": int(self.options.get(CONF_SCAN_POWER, DEFAULT_SCAN_POWER)),
            "energy": int(self.options.get(CONF_SCAN_ENERGY, DEFAULT_SCAN_ENERGY)),
            "history": int(self.options.get(CONF_SCAN_HISTORY, DEFAULT_SCAN_HISTORY)),
            "arc_intensity": int(self.options.get(CONF_SCAN_ARC_INTENSITY, DEFAULT_SCAN_ARC_INTENSITY)),
            "diagnostic": int(self.options.get(CONF_SCAN_BASE, DEFAULT_SCAN_BASE)),
        }

    @property
    def inter_request_delay(self) -> float:
        return int(self.options.get(CONF_INTER_REQUEST_DELAY_MS, DEFAULT_INTER_REQUEST_DELAY_MS)) / 1000

    @property
    def inter_controller_delay(self) -> float:
        return int(self.options.get(CONF_INTER_CONTROLLER_DELAY_MS, DEFAULT_INTER_CONTROLLER_DELAY_MS)) / 1000

    @property
    def max_registers_per_request(self) -> int:
        return int(self.options.get(CONF_MAX_REGISTERS_PER_REQUEST, DEFAULT_MAX_REGISTERS_PER_REQUEST))

    def production_only(self) -> bool:
        return self.sensor_profile == SENSOR_PROFILE_PRODUCTION

    def include_alarm_registers(self) -> bool:
        return bool(
            self.sensor_profile in {SENSOR_PROFILE_STANDARD, SENSOR_PROFILE_DIAGNOSTIC}
            or self.options.get(CONF_ENABLE_ALARM_BINARY_SENSORS, DEFAULT_ENABLE_ALARM_BINARY_SENSORS)
            or self.options.get(CONF_ENABLE_ALARM_TEXT_SENSOR, DEFAULT_ENABLE_ALARM_TEXT_SENSOR)
            or self.options.get(CONF_ENABLE_ALARM_MASKS, DEFAULT_ENABLE_ALARM_MASKS)
        )

    def include_diagnostics(self) -> bool:
        return self.sensor_profile == SENSOR_PROFILE_DIAGNOSTIC

    def enabled_categories(self) -> list[str]:
        categories = ["base"]
        if self.include_alarm_registers():
            categories.append("alarm")
        if self.include_diagnostics():
            categories.append("diagnostic")
        if self.options.get(CONF_ENABLE_POWER, DEFAULT_ENABLE_POWER):
            categories.append("power")
        if self.options.get(CONF_ENABLE_ENERGY, DEFAULT_ENABLE_ENERGY):
            categories.append("energy")
        if self.options.get(CONF_ENABLE_HISTORY, DEFAULT_ENABLE_HISTORY):
            categories.append("history")
        if self.options.get(CONF_ENABLE_ARC_INTENSITY, False):
            categories.append("arc_intensity")
        return categories

    async def start(self) -> None:
        await self._async_load_daily_max()
        self._stopped.clear()
        for category in self.enabled_categories():
            self._tasks.append(self.hass.async_create_task(self._poll_loop(category)))
        await self.async_refresh_all()

    async def stop(self) -> None:
        self._stopped.set()
        for task in self._tasks:
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        await self._daily_max_store.async_save(self._daily_max_payload())

    async def async_refresh_all(self) -> None:
        for category in self.enabled_categories():
            await self._poll_category(category)

    async def _poll_loop(self, category: str) -> None:
        stagger = int(self.options.get(CONF_STARTUP_STAGGER_SECONDS, DEFAULT_STARTUP_STAGGER_SECONDS))
        order = {"base": 0, "power": 1, "alarm": 2, "energy": 3, "diagnostic": 4, "history": 5, "arc_intensity": 6}
        initial_delay = 1 + order.get(category, 0) * stagger
        try:
            await asyncio.wait_for(self._stopped.wait(), timeout=initial_delay)
            return
        except TimeoutError:
            pass

        while not self._stopped.is_set():
            await self._poll_category(category)
            interval = max(5, self.scan_intervals.get(category, 60))
            try:
                await asyncio.wait_for(self._stopped.wait(), timeout=interval)
            except TimeoutError:
                continue

    async def _poll_category(self, category: str) -> None:
        descriptions = [desc for desc in ALL_SENSOR_REGISTERS if desc.category == category]
        if not descriptions:
            return
        for controller in self.controllers:
            controller_descriptions = [
                desc
                for desc in descriptions
                if (_channel_from_key(desc.key) is None or _channel_from_key(desc.key) <= int(controller.channel_count))
            ]
            if not controller_descriptions:
                continue
            try:
                await self._poll_controller_category(controller, category, controller_descriptions)
                self.available[controller.controller_id] = True
                self.last_error[controller.controller_id] = None
                if category == "base":
                    self._update_daily_max(controller)
            except Exception as exc:  # noqa: BLE001
                self.available[controller.controller_id] = False
                self.last_error[controller.controller_id] = str(exc)
                _LOGGER.debug("Polling %s %s failed: %s", controller.display_name, category, exc)
            await asyncio.sleep(self.inter_controller_delay)
        self.callbacks.notify()

    async def _poll_controller_category(
        self,
        controller: ControllerConfig,
        category: str,
        descriptions: list[RegisterDescription],
    ) -> None:
        groups: list[list[RegisterDescription]] = []
        for desc in sorted(descriptions, key=lambda item: item.address):
            if (
                not groups
                or desc.address != groups[-1][-1].address + 1
                or (desc.address - groups[-1][0].address + 1) > self.max_registers_per_request
            ):
                groups.append([desc])
            else:
                groups[-1].append(desc)

        for group in groups:
            start = group[0].address
            count = group[-1].address - start + 1
            values = await self.client.read_holding_registers(controller.slave, start, count)
            for desc in group:
                raw_value = values[desc.address - start]
                self.raw[controller.controller_id][desc.key] = raw_value
                self.data[controller.controller_id][desc.key] = self._decode(raw_value, desc)
            await asyncio.sleep(self.inter_request_delay)

    def _decode(self, raw_value: int, desc: RegisterDescription) -> int | float:
        if desc.data_type == "int16" and raw_value >= 32768:
            raw_value -= 65536
        value: int | float = raw_value * desc.scale
        if desc.precision is not None:
            value = round(value, desc.precision)
        return value

    def get_value(self, controller_id: str, key: str) -> int | float | None:
        return self.data.get(controller_id, {}).get(key)

    def get_raw_value(self, controller_id: str, key: str) -> int | None:
        value = self.raw.get(controller_id, {}).get(key)
        return int(value) if value is not None else None

    def get_daily_max_current(self, controller_id: str, channel: int) -> float | None:
        self._reset_daily_max_if_needed()
        return self.daily_max_current.get(controller_id, {}).get(channel)

    def controller_by_id_or_slave(self, value: str | int) -> ControllerConfig | None:
        value_str = str(value).lower()
        for controller in self.controllers:
            if value_str in {
                controller.controller_id.lower(),
                str(controller.slave),
                controller.name.lower(),
                controller.display_name.lower(),
            }:
                return controller
        return None

    async def async_clear_alarm_trip(self, controller: ControllerConfig) -> None:
        from .const import REGISTER_CLEAR_ALARM_TRIP
        await self.write_register(controller, REGISTER_CLEAR_ALARM_TRIP, 1)

    async def async_clear_arc_history(self, controller: ControllerConfig) -> None:
        from .const import REGISTER_CLEAR_ARC_HISTORY
        await self.write_register(controller, REGISTER_CLEAR_ARC_HISTORY, 1)

    async def async_arc_selftest(self, controller: ControllerConfig) -> None:
        from .const import REGISTER_ARC_SELFTEST
        await self.write_register(controller, REGISTER_ARC_SELFTEST, 1)

    async def write_register(self, controller: ControllerConfig, address: int, value: int) -> None:
        await self.client.write_single_register(controller.slave, address, value)
        await self.async_refresh_all()

    async def _async_load_daily_max(self) -> None:
        stored = await self._daily_max_store.async_load()
        if not isinstance(stored, dict):
            return
        stored_date = str(stored.get("date", ""))
        if stored_date != self._daily_max_date:
            return
        values = stored.get("values", {})
        if not isinstance(values, dict):
            return
        for controller in self.controllers:
            controller_values = values.get(controller.controller_id, {})
            if not isinstance(controller_values, dict):
                continue
            for channel in range(1, controller.channel_count + 1):
                raw = controller_values.get(str(channel), controller_values.get(channel))
                try:
                    self.daily_max_current[controller.controller_id][channel] = max(0.0, float(raw))
                except (TypeError, ValueError):
                    continue

    def _reset_daily_max_if_needed(self) -> None:
        today = dt_util.now().date().isoformat()
        if today == self._daily_max_date:
            return
        self._daily_max_date = today
        for controller in self.controllers:
            self.daily_max_current[controller.controller_id] = {
                channel: 0.0 for channel in range(1, controller.channel_count + 1)
            }
        self._schedule_daily_max_save()

    def _update_daily_max(self, controller: ControllerConfig) -> None:
        self._reset_daily_max_if_needed()
        changed = False
        values = self.daily_max_current.setdefault(controller.controller_id, {})
        for channel in range(1, controller.channel_count + 1):
            current = self.get_value(controller.controller_id, f"ch{channel}_current")
            if current is None:
                continue
            current_float = max(0.0, float(current))
            if current_float > float(values.get(channel, 0.0)):
                values[channel] = round(current_float, 3)
                changed = True
        if changed:
            self._schedule_daily_max_save()

    def _daily_max_payload(self) -> dict[str, Any]:
        return {
            "date": self._daily_max_date,
            "values": {
                controller_id: {str(channel): value for channel, value in values.items()}
                for controller_id, values in self.daily_max_current.items()
            },
        }

    def _schedule_daily_max_save(self) -> None:
        self._daily_max_store.async_delay_save(self._daily_max_payload, 10)
