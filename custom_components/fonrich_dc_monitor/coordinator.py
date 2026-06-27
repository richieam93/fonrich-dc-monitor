from __future__ import annotations

import asyncio
import logging
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
    DEFAULT_TIMEOUT,
)
from .modbus_client import AsyncModbusTcpGateway, CallbackRegistry, FonrichModbusError
from .registers import ALL_SENSOR_REGISTERS, RegisterDescription

_LOGGER = logging.getLogger(__name__)

@dataclass(frozen=True)
class ControllerConfig:
    controller_id: str
    name: str
    slave: int
    enabled: bool = True

class FonrichHub:
    """Shared data hub that staggers Modbus polling by category."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: AsyncModbusTcpGateway,
        controllers: list[ControllerConfig],
        options: dict,
    ) -> None:
        self.hass = hass
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
            "arc_intensity": int(self.options.get(CONF_SCAN_ARC_INTENSITY, DEFAULT_SCAN_ARC_INTENSITY)),
            "history": max(60, int(self.options.get(CONF_SCAN_ENERGY, DEFAULT_SCAN_ENERGY))),
        }

    async def start(self) -> None:
        self._stopped.clear()
        for category in ["alarm", "base", "power", "energy", "history"]:
            self._tasks.append(self.hass.async_create_task(self._poll_loop(category)))
        if self.options.get(CONF_ENABLE_ARC_INTENSITY, False):
            self._tasks.append(self.hass.async_create_task(self._poll_loop("arc_intensity")))
        await self.async_refresh_all()

    async def stop(self) -> None:
        self._stopped.set()
        for task in self._tasks:
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()

    async def async_refresh_all(self) -> None:
        for category in ["alarm", "base", "power", "energy", "history"]:
            await self._poll_category(category)
        if self.options.get(CONF_ENABLE_ARC_INTENSITY, False):
            await self._poll_category("arc_intensity")

    async def _poll_loop(self, category: str) -> None:
        # Small stagger between categories after restart.
        initial_delay = {"alarm": 1, "base": 5, "power": 11, "energy": 17, "history": 23, "arc_intensity": 29}.get(category, 3)
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
            try:
                await self._poll_controller_category(controller, category, descriptions)
                self.available[controller.controller_id] = True
                self.last_error[controller.controller_id] = None
            except Exception as exc:  # noqa: BLE001
                self.available[controller.controller_id] = False
                self.last_error[controller.controller_id] = str(exc)
                _LOGGER.debug("Polling %s %s failed: %s", controller.name, category, exc)
            await asyncio.sleep(0.15)
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
            if not groups or desc.address != groups[-1][-1].address + 1:
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
            await asyncio.sleep(0.08)

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

    async def write_register(self, controller: ControllerConfig, address: int, value: int) -> None:
        await self.client.write_single_register(controller.slave, address, value)
        await self.async_refresh_all()
