from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import async_call_later
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
    CONF_ENABLE_SAFETY_TEST_BUTTONS,
    CONF_INTER_CONTROLLER_DELAY_MS,
    CONF_INTER_REQUEST_DELAY_MS,
    CONF_MAX_REGISTERS_PER_REQUEST,
    CONF_OFFLINE_AFTER_FAILURES,
    CONF_REMOTE_TRIP_ARM_SECONDS,
    CONF_SCAN_ALARM,
    CONF_SCAN_ARC_INTENSITY,
    CONF_SCAN_BASE,
    CONF_SCAN_ENERGY,
    CONF_SCAN_HISTORY,
    CONF_SCAN_POWER,
    CONF_SENSOR_PROFILE,
    CONF_STARTUP_STAGGER_SECONDS,
    CONF_TEST_MESSAGE_SECONDS,
    DEFAULT_DI_DESCRIPTIONS,
    DEFAULT_ENABLE_ALARM_BINARY_SENSORS,
    DEFAULT_ENABLE_ALARM_MASKS,
    DEFAULT_ENABLE_ALARM_TEXT_SENSOR,
    DEFAULT_ENABLE_ENERGY,
    DEFAULT_ENABLE_HISTORY,
    DEFAULT_ENABLE_POWER,
    DEFAULT_ENABLE_SAFETY_TEST_BUTTONS,
    DEFAULT_INTER_CONTROLLER_DELAY_MS,
    DEFAULT_INTER_REQUEST_DELAY_MS,
    DEFAULT_MAX_REGISTERS_PER_REQUEST,
    DEFAULT_OFFLINE_AFTER_FAILURES,
    DEFAULT_REMOTE_TRIP_ARM_SECONDS,
    DEFAULT_SCAN_ALARM,
    DEFAULT_SCAN_ARC_INTENSITY,
    DEFAULT_SCAN_BASE,
    DEFAULT_SCAN_ENERGY,
    DEFAULT_SCAN_HISTORY,
    DEFAULT_SCAN_POWER,
    DEFAULT_SENSOR_PROFILE,
    DEFAULT_STARTUP_STAGGER_SECONDS,
    DEFAULT_TEST_MESSAGE_SECONDS,
    DOMAIN,
    REGISTER_ALARM_FUNCTION_MGMT_2,
    REGISTER_ARC_SELFTEST,
    REGISTER_CLEAR_ALARM_TRIP,
    REGISTER_CLEAR_ARC_HISTORY,
    REGISTER_REMOTE_MANUAL_TRIP,
    REGISTER_TRIP_ACTION_MGMT_2,
    REMOTE_TRIP_ENABLE_BIT,
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
    di_descriptions: tuple[str, ...] = DEFAULT_DI_DESCRIPTIONS

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

    def di_description(self, index: int) -> str:
        if index < 1 or index > 4:
            return f"DI{index}"
        if index - 1 < len(self.di_descriptions):
            description = str(self.di_descriptions[index - 1]).strip()
            if description:
                return description
        return f"DI{index}"


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
        self.last_success: dict[str, str | None] = {c.controller_id: None for c in self.controllers}
        self.last_attempt: dict[str, str | None] = {c.controller_id: None for c in self.controllers}
        self.consecutive_errors: dict[str, int] = {c.controller_id: 0 for c in self.controllers}
        self.successful_polls: dict[str, int] = {c.controller_id: 0 for c in self.controllers}
        self.failed_polls: dict[str, int] = {c.controller_id: 0 for c in self.controllers}
        self.category_errors: dict[str, dict[str, str]] = {c.controller_id: {} for c in self.controllers}
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
        self._remote_trip_armed_until: dict[str, datetime | None] = {
            c.controller_id: None for c in self.controllers
        }
        self._test_messages: dict[str, dict[str, tuple[str, datetime]]] = {
            c.controller_id: {} for c in self.controllers
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
            "safety": 60,
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

    @property
    def offline_after_failures(self) -> int:
        return max(1, int(self.options.get(CONF_OFFLINE_AFTER_FAILURES, DEFAULT_OFFLINE_AFTER_FAILURES)))

    @property
    def safety_test_buttons_enabled(self) -> bool:
        return bool(self.options.get(CONF_ENABLE_SAFETY_TEST_BUTTONS, DEFAULT_ENABLE_SAFETY_TEST_BUTTONS))

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
        if self.safety_test_buttons_enabled:
            categories.append("safety")
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
        order = {"base": 0, "power": 1, "alarm": 2, "safety": 3, "energy": 4, "diagnostic": 5, "history": 6, "arc_intensity": 7}
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
            controller_id = controller.controller_id
            self.last_attempt[controller_id] = dt_util.now().isoformat()
            try:
                await self._poll_controller_category(controller, category, controller_descriptions)
                self.successful_polls[controller_id] += 1
                self.category_errors[controller_id].pop(category, None)
                if category == "base":
                    self.available[controller_id] = True
                    self.last_success[controller_id] = dt_util.now().isoformat()
                    self.last_error[controller_id] = None
                    self.consecutive_errors[controller_id] = 0
                    self._update_daily_max(controller)
            except Exception as exc:  # noqa: BLE001
                error_text = f"{category}: {exc}"
                self.failed_polls[controller_id] += 1
                self.category_errors[controller_id][category] = str(exc)
                self.last_error[controller_id] = error_text
                if category == "base":
                    self.consecutive_errors[controller_id] += 1
                    if self.consecutive_errors[controller_id] >= self.offline_after_failures:
                        self.available[controller_id] = False
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

    def remote_trip_configuration(self, controller_id: str) -> dict[str, bool | int | None]:
        """Return the cached remote-trip enable state without changing protection settings."""
        alarm_raw = self.get_raw_value(controller_id, "remote_trip_alarm_enable_config")
        action_raw = self.get_raw_value(controller_id, "remote_trip_action_enable_config")
        alarm_enabled = None if alarm_raw is None else bool(alarm_raw & REMOTE_TRIP_ENABLE_BIT)
        action_enabled = None if action_raw is None else bool(action_raw & REMOTE_TRIP_ENABLE_BIT)
        ready = bool(alarm_enabled and action_enabled)
        return {
            "alarm_register": alarm_raw,
            "action_register": action_raw,
            "alarm_enabled": alarm_enabled,
            "action_enabled": action_enabled,
            "ready": ready,
        }

    async def _async_read_remote_trip_configuration(self, controller: ControllerConfig) -> dict[str, bool | int | None]:
        """Read and cache both documented remote-trip enable registers."""
        alarm_raw = (
            await self.client.read_holding_registers(
                controller.slave, REGISTER_ALARM_FUNCTION_MGMT_2, 1
            )
        )[0]
        action_raw = (
            await self.client.read_holding_registers(
                controller.slave, REGISTER_TRIP_ACTION_MGMT_2, 1
            )
        )[0]
        controller_id = controller.controller_id
        self.raw[controller_id]["remote_trip_alarm_enable_config"] = alarm_raw
        self.raw[controller_id]["remote_trip_action_enable_config"] = action_raw
        self.data[controller_id]["remote_trip_alarm_enable_config"] = alarm_raw
        self.data[controller_id]["remote_trip_action_enable_config"] = action_raw
        return self.remote_trip_configuration(controller_id)

    @staticmethod
    def _remote_trip_missing_config(config: dict[str, bool | int | None]) -> list[str]:
        missing: list[str] = []
        if not config.get("alarm_enabled"):
            missing.append("Register 2849 Bit 14")
        if not config.get("action_enabled"):
            missing.append("Register 2852 Bit 14")
        return missing

    async def async_clear_alarm_trip(self, controller: ControllerConfig) -> None:
        await self.write_register(controller, REGISTER_CLEAR_ALARM_TRIP, 1)

    async def async_clear_arc_history(self, controller: ControllerConfig) -> None:
        await self.write_register(controller, REGISTER_CLEAR_ARC_HISTORY, 1)

    async def async_arc_selftest(self, controller: ControllerConfig) -> None:
        await self.write_register(controller, REGISTER_ARC_SELFTEST, 1)

    async def write_register(self, controller: ControllerConfig, address: int, value: int) -> None:
        if not self.available.get(controller.controller_id, False):
            raise HomeAssistantError(f"{controller.display_name} ist offline.")
        await self.client.write_single_register(controller.slave, address, value)
        await self.async_refresh_all()

    # ---------------------------------------------------------------------
    # Safety-related tests
    # ---------------------------------------------------------------------
    def remote_trip_armed_until(self, controller_id: str) -> str | None:
        until = self._remote_trip_armed_until.get(controller_id)
        if until is None or until <= dt_util.now():
            self._remote_trip_armed_until[controller_id] = None
            return None
        return until.isoformat()

    def remote_trip_is_armed(self, controller_id: str) -> bool:
        return self.remote_trip_armed_until(controller_id) is not None

    async def async_arm_remote_trip(self, controller: ControllerConfig) -> None:
        if not self.safety_test_buttons_enabled:
            raise HomeAssistantError("Sicherheits-Testbuttons sind in den Optionen deaktiviert.")
        if not self.available.get(controller.controller_id, False):
            raise HomeAssistantError(f"{controller.display_name} ist offline.")
        config = await self._async_read_remote_trip_configuration(controller)
        if not config["ready"]:
            missing = self._remote_trip_missing_config(config)
            raise HomeAssistantError(
                "Remote-Trip ist im Fonrich nicht vollständig freigegeben ("
                + ", ".join(missing)
                + "). Die Integration ändert diese Schutzkonfiguration aus Sicherheitsgründen nicht automatisch."
            )
        seconds = max(5, min(60, int(self.options.get(CONF_REMOTE_TRIP_ARM_SECONDS, DEFAULT_REMOTE_TRIP_ARM_SECONDS))))
        until = dt_util.now() + timedelta(seconds=seconds)
        self._remote_trip_armed_until[controller.controller_id] = until
        self._set_test_message(
            controller,
            "remote_trip_armed",
            f"TEST: Hauptschalter-Auslösung bei {controller.display_name} für {seconds} Sekunden freigegeben",
            seconds,
        )
        async_call_later(
            self.hass,
            seconds + 0.2,
            lambda _now: self._expire_remote_trip_arm(controller.controller_id, until),
        )
        self.callbacks.notify()

    def _expire_remote_trip_arm(self, controller_id: str, expected_until: datetime) -> None:
        if self._remote_trip_armed_until.get(controller_id) == expected_until:
            self._remote_trip_armed_until[controller_id] = None
            self._test_messages.get(controller_id, {}).pop("remote_trip_armed", None)
            self.callbacks.notify()

    async def async_remote_trip_test(self, controller: ControllerConfig) -> None:
        """Trigger the documented remote manual trip command (register 3076).

        The action is deliberately guarded by an integration option, a temporary
        arm button and verification of the two documented enable bits. The
        integration never enables these protection bits automatically.
        """
        if not self.safety_test_buttons_enabled:
            raise HomeAssistantError("Sicherheits-Testbuttons sind in den Optionen deaktiviert.")
        if not self.available.get(controller.controller_id, False):
            raise HomeAssistantError(f"{controller.display_name} ist offline.")
        if not self.remote_trip_is_armed(controller.controller_id):
            raise HomeAssistantError("Zuerst 'Hauptschalter-Test freigeben' drücken. Die Freigabe gilt nur kurz.")

        config = await self._async_read_remote_trip_configuration(controller)
        if not config["ready"]:
            self._remote_trip_armed_until[controller.controller_id] = None
            self._test_messages.get(controller.controller_id, {}).pop("remote_trip_armed", None)
            self.callbacks.notify()
            missing = self._remote_trip_missing_config(config)
            raise HomeAssistantError(
                "Remote-Trip ist im Fonrich nicht vollständig freigegeben ("
                + ", ".join(missing)
                + "). Die Integration ändert diese Schutzkonfiguration aus Sicherheitsgründen nicht automatisch."
            )

        await self.client.write_single_register(controller.slave, REGISTER_REMOTE_MANUAL_TRIP, 1)
        self._remote_trip_armed_until[controller.controller_id] = None
        self._test_messages.get(controller.controller_id, {}).pop("remote_trip_armed", None)
        self._set_test_message(
            controller,
            "remote_trip_executed",
            f"TEST: Hauptschalter-Auslösung bei {controller.display_name} wurde gesendet",
            int(self.options.get(CONF_TEST_MESSAGE_SECONDS, DEFAULT_TEST_MESSAGE_SECONDS)),
        )
        self.callbacks.notify()

    async def async_lightning_protection_message_test(self, controller: ControllerConfig) -> None:
        """Create a clearly marked HA-only lightning protection test message.

        The FR-DCMG-MMPS documentation exposes lightning arrester status through
        physical DI contacts but no Modbus command that can electrically trip a
        surge protection device. This action therefore tests dashboards and
        notifications only and never writes a hardware output.
        """
        if not self.safety_test_buttons_enabled:
            raise HomeAssistantError("Sicherheits-Testbuttons sind in den Optionen deaktiviert.")
        seconds = max(10, min(600, int(self.options.get(CONF_TEST_MESSAGE_SECONDS, DEFAULT_TEST_MESSAGE_SECONDS))))
        self._set_test_message(
            controller,
            "lightning_protection",
            f"TEST: Blitzschutz-Meldung bei {controller.display_name} (nur Home Assistant, keine Hardware-Auslösung)",
            seconds,
        )
        self.callbacks.notify()

    async def async_clear_test_messages(self, controller: ControllerConfig) -> None:
        self._test_messages[controller.controller_id] = {}
        self._remote_trip_armed_until[controller.controller_id] = None
        self.callbacks.notify()

    def _set_test_message(self, controller: ControllerConfig, key: str, text: str, seconds: int) -> None:
        expires = dt_util.now() + timedelta(seconds=max(1, seconds))
        self._test_messages.setdefault(controller.controller_id, {})[key] = (text, expires)
        async_call_later(
            self.hass,
            max(1, seconds) + 0.2,
            lambda _now: self._expire_test_message(controller.controller_id, key, expires),
        )

    def _expire_test_message(self, controller_id: str, key: str, expected_expiry: datetime) -> None:
        current = self._test_messages.get(controller_id, {}).get(key)
        if current and current[1] == expected_expiry:
            self._test_messages[controller_id].pop(key, None)
            self.callbacks.notify()

    def get_test_messages(self, controller_id: str) -> list[str]:
        now = dt_util.now()
        messages = self._test_messages.setdefault(controller_id, {})
        expired = [key for key, (_text, expiry) in messages.items() if expiry <= now]
        for key in expired:
            messages.pop(key, None)
        return [text for text, _expiry in messages.values()]

    # ---------------------------------------------------------------------
    # Daily maximum current persistence
    # ---------------------------------------------------------------------
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
