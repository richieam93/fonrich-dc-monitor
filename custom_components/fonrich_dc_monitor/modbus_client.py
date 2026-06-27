from __future__ import annotations

import asyncio
import logging
import struct
from collections.abc import Callable
from dataclasses import dataclass

_LOGGER = logging.getLogger(__name__)

class FonrichModbusError(Exception):
    """Raised when Modbus communication fails."""

@dataclass
class ModbusTcpResponse:
    unit_id: int
    function: int
    values: list[int]
    raw: bytes

class AsyncModbusTcpGateway:
    """Small async Modbus TCP client for HF2211 Modbus gateway mode."""

    def __init__(self, host: str, port: int, timeout: float, retries: int) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout
        self.retries = retries
        self._transaction_id = 0
        self._lock = asyncio.Lock()

    async def read_holding_registers(self, unit_id: int, address: int, count: int = 1) -> list[int]:
        return await self._request_read(unit_id, 3, address, count)

    async def write_single_register(self, unit_id: int, address: int, value: int) -> None:
        async with self._lock:
            last_error: Exception | None = None
            for attempt in range(self.retries + 1):
                try:
                    await self._write_single_register_locked(unit_id, address, value)
                    return
                except Exception as exc:  # noqa: BLE001
                    last_error = exc
                    if attempt < self.retries:
                        await asyncio.sleep(0.3)
            raise FonrichModbusError(f"Write failed unit={unit_id} address={address}: {last_error}") from last_error

    async def _request_read(self, unit_id: int, function: int, address: int, count: int) -> list[int]:
        async with self._lock:
            last_error: Exception | None = None
            for attempt in range(self.retries + 1):
                try:
                    response = await self._read_locked(unit_id, function, address, count)
                    return response.values
                except Exception as exc:  # noqa: BLE001
                    last_error = exc
                    if attempt < self.retries:
                        await asyncio.sleep(0.3)
            raise FonrichModbusError(f"Read failed unit={unit_id} address={address}: {last_error}") from last_error

    async def _read_locked(self, unit_id: int, function: int, address: int, count: int) -> ModbusTcpResponse:
        self._transaction_id = (self._transaction_id + 1) % 65536
        transaction_id = self._transaction_id or 1
        pdu = struct.pack(">BHH", function, address, count)
        request = struct.pack(">HHHB", transaction_id, 0, len(pdu) + 1, unit_id) + pdu
        response = await self._send_request(request)
        return self._parse_read_response(response, transaction_id, unit_id, function, count)

    async def _write_single_register_locked(self, unit_id: int, address: int, value: int) -> None:
        self._transaction_id = (self._transaction_id + 1) % 65536
        transaction_id = self._transaction_id or 1
        pdu = struct.pack(">BHH", 6, address, value)
        request = struct.pack(">HHHB", transaction_id, 0, len(pdu) + 1, unit_id) + pdu
        response = await self._send_request(request)
        if len(response) < 12:
            raise FonrichModbusError("short write response")
        rx_transaction, protocol, length, rx_unit = struct.unpack(">HHHB", response[:7])
        if rx_transaction != transaction_id or protocol != 0 or rx_unit != unit_id:
            raise FonrichModbusError("invalid write response header")
        function, rx_address, rx_value = struct.unpack(">BHH", response[7:12])
        if function & 0x80:
            code = response[8] if len(response) > 8 else None
            raise FonrichModbusError(f"Modbus exception {code}")
        if function != 6 or rx_address != address or rx_value != value:
            raise FonrichModbusError("invalid write echo")

    async def _send_request(self, request: bytes) -> bytes:
        writer: asyncio.StreamWriter | None = None
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port), timeout=self.timeout
            )
            writer.write(request)
            await asyncio.wait_for(writer.drain(), timeout=self.timeout)
            header = await asyncio.wait_for(reader.readexactly(7), timeout=self.timeout)
            _transaction, _protocol, length = struct.unpack(">HHH", header[:6])
            body = await asyncio.wait_for(reader.readexactly(length - 1), timeout=self.timeout)
            return header + body
        finally:
            if writer is not None:
                writer.close()
                try:
                    await writer.wait_closed()
                except Exception:  # noqa: BLE001
                    pass

    def _parse_read_response(
        self,
        response: bytes,
        transaction_id: int,
        unit_id: int,
        function: int,
        count: int,
    ) -> ModbusTcpResponse:
        if len(response) < 9:
            raise FonrichModbusError("short response")
        rx_transaction, protocol, _length, rx_unit = struct.unpack(">HHHB", response[:7])
        if rx_transaction != transaction_id or protocol != 0 or rx_unit != unit_id:
            raise FonrichModbusError("invalid response header")
        rx_function = response[7]
        if rx_function & 0x80:
            code = response[8] if len(response) > 8 else None
            raise FonrichModbusError(f"Modbus exception {code}")
        if rx_function != function:
            raise FonrichModbusError("unexpected function")
        byte_count = response[8]
        if byte_count != count * 2 or len(response) < 9 + byte_count:
            raise FonrichModbusError("invalid byte count")
        values = [struct.unpack(">H", response[9 + i * 2: 11 + i * 2])[0] for i in range(count)]
        return ModbusTcpResponse(rx_unit, rx_function, values, response)

class CallbackRegistry:
    def __init__(self) -> None:
        self._callbacks: set[Callable[[], None]] = set()

    def add(self, callback: Callable[[], None]) -> Callable[[], None]:
        self._callbacks.add(callback)
        return lambda: self._callbacks.discard(callback)

    def notify(self) -> None:
        for callback in list(self._callbacks):
            callback()
