from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass

from homeassistant.core import HomeAssistant

from .const import (
    CONF_ENABLE_ARC_INTENSITY,
    CONF_RETRIES,
    CONF_SCAN_ALARM,
    CONF_SCAN_ARC_INTENSITY,
    CONF_SCAN_BASE,
    CONF_SCAN_ENERGY,
    CONF_SCAN_POWER,
    CONF_TIMEOUT,
    DEFAULT_SCAN_ALARM,
    DEFAULT_SCAN_ARC_INTENSITY,
    DEFAULT_SCAN_BASE,
    DEFAULT_SCAN_ENERGY,
    DEFAULT_SCAN_POWER,
    CONF_SCAN_HISTORY,
    CONF_INTER_REQUEST_DELAY_MS,
    CONF_INTER_CONTROLLER_DELAY_MS,
    CONF_STARTUP_STAGGER_SECONDS,
    CONF_MAX_REGISTERS_PER_REQUEST,
    CONF_ENABLE_POWER,
    CONF_ENABLE_ENERGY,
    CONF_ENABLE_HISTORY,
    CONF_ENABLE_ALARM_MASKS,
    DEFAULT_SCAN_HISTORY,
    DEFAULT_INTER_REQUEST_DELAY_MS,
    DEFAULT_INTER_CONTROLLER_DELAY_MS,
    DEFAULT_STARTUP_STAGGER_SECONDS,
    DEFAULT_MAX_REGISTERS_PER_REQUEST,
    DEFAULT_ENABLE_POWER,
    DEFAULT_ENABLE_ENERGY,
    DEFAULT_ENABLE_HISTORY,
    DEFAULT_ENABLE_ALARM_MASKS,
    DEFAULT_TIMEOUT,
)
from .modbus_client import AsyncModbusTcpGateway, CallbackRegistry, FonrichModbusError
from .registers import ALL_SENSOR_REGISTERS, RegisterDescription

_LOGGER = logging.getLogger(__name__)

_CHANNEL_RE = re.compile(r"^ch(\d+)_")

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

    def channel_description(self, channel: int) -> str:
        if channel < 1 or channel > self.channel_count:
            return ""
        index = channel - 1
        if index < len(self.channel_descriptions):
            return self.channel_descriptions[index]
        return ""

class FonrichHub:
    """Shared data hub that staggers Modbus polling by category."""

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

    @property
    def scan_intervals(self) -> dict[str, int]:
        return {
            "alarm": int(self.options.get(CONF_SCAN_ALARM, DEFAULT_SCAN_ALARM)),
            "base": int(self.options.get(CONF_SCAN_BASE, DEFAULT_SCAN_BASE)),
            "power": int(self.options.get(CONF_SCAN_POWER, DEFAULT_SCAN_POWER)),
            "energy": int(self.options.get(CONF_SCAN_ENERGY, DEFAULT_SCAN_ENERGY)),
            "history": int(self.options.get(CONF_SCAN_HISTORY, DEFAULT_SCAN_HISTORY)),
            "arc_intensity": int(self.options.get(CONF_SCAN_ARC_INTENSITY, DEFAULT_SCAN_ARC_INTENSITY)),
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

    def enabled_categories(self) -> list[str]:
        categories = ["alarm", "base"]
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

    async def async_refresh_all(self) -> None:
        for category in self.enabled_categories():
            await self._poll_category(category)

    async def _poll_loop(self, category: str) -> None:
        # Small stagger between categories after restart.
        stagger = int(self.options.get(CONF_STARTUP_STAGGER_SECONDS, DEFAULT_STARTUP_STAGGER_SECONDS))
        order = {"alarm": 0, "base": 1, "power": 2, "energy": 3, "history": 4, "arc_intensity": 5}
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
            except Exception as exc:  # noqa: BLE001
                self.available[controller.controller_id] = False
                self.last_error[controller.controller_id] = str(exc)
                _LOGGER.debug("Polling %s %s failed: %s", controller.name, category, exc)
            await asyncio.sleep(self.inter_controller_delay)
        self.callbacks.notify()

    async def _poll_controller_category(
        self,
        controller: ControllerConfig,
        category: str,
        descriptions: list[RegisterDescription],
    ) -> None:
        # Read contiguous register groups rather than one request per entity.
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

    def controller_by_id_or_slave(self, value: str | int) -> ControllerConfig | None:
        value_str = str(value).lower()
        for controller in self.controllers:
            if value_str in {controller.controller_id.lower(), str(controller.slave), controller.name.lower()}:
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
