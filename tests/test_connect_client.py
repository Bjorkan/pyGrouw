"""Tests for the Robotic Mower Connect BLE client."""

from __future__ import annotations

import asyncio
from typing import Any

from bleak import BleakError
import pytest

from pygrouw.connect_client import GrouwConnectBleMowerClient
from pygrouw.connect_protocol import encode_connect_message
from pygrouw.const import (
    CONNECT_READ_CHARACTERISTIC_UUID,
    CONNECT_WRITE_CHARACTERISTIC_UUID,
)
from pygrouw.exceptions import (
    GrouwBleGattError,
    GrouwBleOperationIndeterminate,
    GrouwBleVerificationError,
)


def test_connect_query_reassembles_notifications_and_disconnects() -> None:
    class _BleClient:
        def __init__(self) -> None:
            self.handler: Any = None
            self.writes: list[tuple[str, bytes, bool]] = []
            self.disconnected = False

        async def start_notify(self, uuid: str, handler: Any) -> None:
            assert uuid == CONNECT_READ_CHARACTERISTIC_UUID
            self.handler = handler

        async def stop_notify(self, uuid: str) -> None:
            assert uuid == CONNECT_READ_CHARACTERISTIC_UUID

        async def write_gatt_char(self, uuid: str, data: bytes, *, response: bool) -> None:
            self.writes.append((uuid, data, response))
            framed = b"".join(encode_connect_message({"cmd": 500, "power": 88}))
            self.handler(1, bytearray(framed[:7]))
            self.handler(1, bytearray(framed[7:]))

        async def disconnect(self) -> None:
            self.disconnected = True

    async def run() -> None:
        mower_client = GrouwConnectBleMowerClient("AA:BB:CC:DD:EE:FF")
        ble_client = _BleClient()

        async def connect(_timeout: float) -> _BleClient:
            return ble_client

        async def no_mtu(_client: Any) -> None:
            return None

        mower_client._establish_connection = connect  # type: ignore[method-assign]
        mower_client._request_mtu_with_log = no_mtu  # type: ignore[method-assign]

        result = await mower_client.async_get_all_info()

        assert result["cmd"] == 500
        assert result["battery_level"] == 88
        assert ble_client.writes[0][0] == CONNECT_WRITE_CHARACTERISTIC_UUID
        assert ble_client.writes[0][2] is True
        assert ble_client.disconnected is True

    asyncio.run(run())


def test_connect_command_accepts_command_specific_result() -> None:
    async def run() -> None:
        client = GrouwConnectBleMowerClient("AA:BB:CC:DD:EE:FF")
        seen: dict[str, Any] = {}

        async def request(
            packets: list[bytes],
            *,
            expected_cmd: int | set[int] | None,
            **_kwargs: Any,
        ) -> dict[str, Any]:
            seen["packets"] = packets
            seen["expected_cmd"] = expected_cmd
            return {"cmd": 10101, "result": True}

        async def all_info() -> dict[str, Any]:
            return {"cmd": 500, "power": 70}

        client.async_request_connect = request  # type: ignore[method-assign]
        client.async_get_all_info = all_info  # type: ignore[method-assign]

        result = await client.async_command("start")

        assert seen["expected_cmd"] == {400, 10101}
        assert result == {"cmd": 500, "power": 70}

    asyncio.run(run())


def test_connect_pin_rejection_does_not_update_client_pin() -> None:
    async def run() -> None:
        client = GrouwConnectBleMowerClient("AA:BB:CC:DD:EE:FF", pin="1234")

        async def request(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
            return {"cmd": 504, "passwd_res": False}

        client.async_request_connect = request  # type: ignore[method-assign]

        with pytest.raises(GrouwBleVerificationError, match="rejected pin"):
            await client.async_set_pin("4321")
        assert client.pin == "1234"

    asyncio.run(run())


def test_connect_notify_setup_maps_backend_error_and_disconnects() -> None:
    class _BleClient:
        disconnected = False

        async def start_notify(self, _uuid: str, _handler: Any) -> None:
            raise BleakError("notify unavailable")

        async def disconnect(self) -> None:
            self.disconnected = True

    async def run() -> None:
        mower_client = GrouwConnectBleMowerClient("AA:BB:CC:DD:EE:FF")
        ble_client = _BleClient()

        async def connect(_timeout: float) -> _BleClient:
            return ble_client

        async def no_mtu(_client: Any) -> None:
            return None

        mower_client._establish_connection = connect  # type: ignore[method-assign]
        mower_client._request_mtu_with_log = no_mtu  # type: ignore[method-assign]

        with pytest.raises(GrouwBleGattError, match="notify setup failed"):
            await mower_client.async_get_all_info()
        assert ble_client.disconnected is True

    asyncio.run(run())


def test_connect_timeout_after_mutating_write_is_indeterminate() -> None:
    class _BleClient:
        async def start_notify(self, _uuid: str, _handler: Any) -> None:
            return None

        async def stop_notify(self, _uuid: str) -> None:
            return None

        async def write_gatt_char(self, _uuid: str, _data: bytes, *, response: bool) -> None:
            assert response is True

        async def disconnect(self) -> None:
            return None

    async def run() -> None:
        client = GrouwConnectBleMowerClient("AA:BB:CC:DD:EE:FF")
        ble_client = _BleClient()

        async def connect(_timeout: float) -> _BleClient:
            return ble_client

        async def no_mtu(_client: Any) -> None:
            return None

        client._establish_connection = connect  # type: ignore[method-assign]
        client._request_mtu_with_log = no_mtu  # type: ignore[method-assign]

        with pytest.raises(GrouwBleOperationIndeterminate) as exc_info:
            await client.async_request_connect(
                encode_connect_message({"cmd": 0, "rain_en": True}),
                expected_cmd=400,
                timeout=0.01,
                command_name="rain",
                mutation=True,
            )
        assert exc_info.value.completed_steps == ("rain",)
        assert exc_info.value.write_may_have_completed is True

    asyncio.run(run())
