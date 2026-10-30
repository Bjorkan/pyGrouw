"""BLE client for Grouw mowers supported by Robotic Mower Connect."""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

from bleak import BleakClient

from .client import BLE_BACKEND_EXCEPTIONS, GrouwBleMowerClient
from .connect_protocol import (
    CONNECT_QUERY_ALL_INFO,
    CONNECT_QUERY_DEVICE_INFO,
    CONNECT_QUERY_FEATURES,
    CONNECT_QUERY_MULTI_AREA,
    CONNECT_QUERY_RAIN,
    CONNECT_QUERY_SCHEDULE,
    CONNECT_QUERY_STATUS,
    CONNECT_RESPONSE_ACK,
    CONNECT_RESPONSE_ALL_INFO,
    CONNECT_RESPONSE_DEVICE_INFO,
    CONNECT_RESPONSE_FEATURES,
    CONNECT_RESPONSE_MULTI_AREA,
    CONNECT_RESPONSE_RAIN,
    CONNECT_RESPONSE_SCHEDULE,
    CONNECT_RESPONSE_STATUS,
    ConnectFrameDecoder,
    encode_connect_device_name,
    encode_connect_language,
    encode_connect_led,
    encode_connect_message,
    encode_connect_multi_area,
    encode_connect_pin,
    encode_connect_query,
    encode_connect_rain,
    encode_connect_schedule,
    encode_connect_schedule_pause,
    encode_connect_time,
    encode_connect_ultrasonic,
    encode_connect_wifi,
    encode_connect_work_mode,
    parse_connect_payload,
)
from .const import (
    CONNECT_READ_CHARACTERISTIC_UUID,
    CONNECT_WRITE_CHARACTERISTIC_UUID,
    DEFAULT_BLE_TIMEOUT,
    DEFAULT_CHUNK_DELAY,
)
from .exceptions import (
    GrouwBleError,
    GrouwBleGattError,
    GrouwBleOperationIndeterminate,
    GrouwBleTimeout,
    GrouwBleVerificationError,
)


class GrouwConnectBleMowerClient(GrouwBleMowerClient):
    """Local client for the newer FFF0/JSON Grouw BLE generation."""

    async def async_request_connect(
        self,
        packets: list[bytes],
        *,
        expected_cmd: int | set[int] | None,
        timeout: float = DEFAULT_BLE_TIMEOUT,
        command_name: str = "connect",
        mutation: bool = False,
    ) -> dict[str, Any]:
        """Write one framed JSON request and await its matching response."""
        async with self._request_lock:
            self._tx_counter += 1
            self._tx_id = self._tx_counter
            queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
            decoder = ConnectFrameDecoder()
            loop = asyncio.get_running_loop()

            def notification_handler(_sender: int | str, data: bytearray) -> None:
                for payload in decoder.feed(data):
                    message = parse_connect_payload(payload)
                    if message is not None:
                        loop.call_soon_threadsafe(queue.put_nowait, message)

            client: BleakClient | None = None
            notify_started = False
            packets_written = 0
            try:
                client = await self._establish_connection(timeout)
                await self._request_mtu_with_log(client)
                try:
                    await client.start_notify(
                        CONNECT_READ_CHARACTERISTIC_UUID, notification_handler
                    )
                except BLE_BACKEND_EXCEPTIONS as err:
                    raise GrouwBleGattError(
                        f"GATT notify setup failed for {command_name} on {self.address}: {err}"
                    ) from err
                notify_started = True
                for packet in packets:
                    try:
                        await client.write_gatt_char(
                            CONNECT_WRITE_CHARACTERISTIC_UUID, packet, response=True
                        )
                        packets_written += 1
                    except BLE_BACKEND_EXCEPTIONS as err:
                        raise GrouwBleGattError(
                            f"GATT write failed for {command_name} on {self.address}: {err}"
                        ) from err
                    if len(packets) > 1:
                        await asyncio.sleep(DEFAULT_CHUNK_DELAY)
                return await self._wait_for_connect_response(
                    queue, expected_cmd=expected_cmd, timeout=timeout
                )
            except (GrouwBleGattError, GrouwBleTimeout) as err:
                if mutation and packets_written:
                    raise GrouwBleOperationIndeterminate(
                        f"Connect operation {command_name} may have been applied",
                        completed_steps=(command_name,) if packets_written == len(packets) else (),
                        failed_step=command_name,
                        write_may_have_completed=True,
                    ) from err
                raise
            finally:
                if client is not None:
                    if notify_started:
                        try:
                            await client.stop_notify(CONNECT_READ_CHARACTERISTIC_UUID)
                        except Exception:  # noqa: BLE001, S110
                            pass
                    try:
                        await client.disconnect()
                    except Exception:  # noqa: BLE001, S110
                        pass

    async def _wait_for_connect_response(
        self,
        queue: asyncio.Queue[dict[str, Any]],
        *,
        expected_cmd: int | set[int] | None,
        timeout: float,
    ) -> dict[str, Any]:
        deadline = asyncio.get_running_loop().time() + timeout
        while True:
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                raise GrouwBleTimeout(f"Timeout waiting for notification from {self.address}")
            try:
                message = await asyncio.wait_for(queue.get(), remaining)
            except TimeoutError as err:
                raise GrouwBleTimeout(
                    f"Timeout waiting for notification from {self.address}"
                ) from err
            command = message.get("cmd")
            if (
                expected_cmd is None
                or command == expected_cmd
                or (isinstance(expected_cmd, set) and command in expected_cmd)
            ):
                return message

    async def async_query(self, command: int, response_command: int | set[int]) -> dict[str, Any]:
        """Send a numeric Connect query and await its response command."""
        return await self.async_request_connect(
            encode_connect_query(command),
            expected_cmd=response_command,
            command_name=f"query_{command}",
        )

    async def async_get_all_info(self) -> dict[str, Any]:
        return await self.async_query(CONNECT_QUERY_ALL_INFO, CONNECT_RESPONSE_ALL_INFO)

    async def async_get_status(self) -> dict[str, Any]:
        # The APK parser recognizes both a direct 201 status and the 501 BLE
        # status family, so tolerate either firmware response shape.
        return await self.async_query(
            CONNECT_QUERY_STATUS, {CONNECT_QUERY_STATUS, CONNECT_RESPONSE_STATUS}
        )

    async def async_get_connect_device_info(self) -> dict[str, Any]:
        return await self.async_query(CONNECT_QUERY_DEVICE_INFO, CONNECT_RESPONSE_DEVICE_INFO)

    async def async_get_features(self) -> dict[str, Any]:
        return await self.async_query(CONNECT_QUERY_FEATURES, CONNECT_RESPONSE_FEATURES)

    async def async_get_rain(self) -> dict[str, Any]:
        return await self.async_query(CONNECT_QUERY_RAIN, CONNECT_RESPONSE_RAIN)

    async def async_get_multi_area(self) -> dict[str, Any]:
        return await self.async_query(CONNECT_QUERY_MULTI_AREA, CONNECT_RESPONSE_MULTI_AREA)

    async def async_get_schedule(self) -> dict[str, Any]:
        return await self.async_query(CONNECT_QUERY_SCHEDULE, CONNECT_RESPONSE_SCHEDULE)

    async def _async_set(
        self,
        packets: list[bytes],
        name: str,
        *,
        expected_cmd: int | set[int] = CONNECT_RESPONSE_ACK,
    ) -> dict[str, Any]:
        acknowledgement = await self.async_request_connect(
            packets,
            expected_cmd=expected_cmd,
            command_name=name,
            mutation=True,
        )
        if acknowledgement.get("result") is False:
            raise GrouwBleVerificationError(f"Connect mower rejected {name}")
        if acknowledgement.get("cmd") == 504 and acknowledgement.get("passwd_res") is False:
            raise GrouwBleVerificationError("Connect mower rejected pin")
        return await self.async_get_all_info()

    async def async_command(self, command: str, point: int | None = None) -> dict[str, Any]:
        normalized = command.strip().lower()
        response_commands = {
            "pause": 10100,
            "stop": 10100,
            "resume": 10101,
            "start": 10101,
            "work": 10101,
            "dock": 10102,
            "home": 10102,
        }
        expected = {CONNECT_RESPONSE_ACK}
        if response := response_commands.get(normalized):
            expected.add(response)
        return await self._async_set(
            encode_connect_work_mode(command, point), command, expected_cmd=expected
        )

    async def async_set_rain(self, enabled: bool, delay: int) -> dict[str, Any]:
        return await self._async_set(encode_connect_rain(enabled, delay), "rain")

    async def async_set_ultrasonic(self, enabled: bool, level: int) -> dict[str, Any]:
        return await self._async_set(encode_connect_ultrasonic(enabled, level), "ultrasonic")

    async def async_set_language(self, language: str | int) -> dict[str, Any]:
        return await self._async_set(encode_connect_language(language), "language")

    async def async_set_pin(self, pin: str) -> dict[str, Any]:
        result = await self._async_set(
            encode_connect_pin(pin), "pin", expected_cmd={CONNECT_RESPONSE_ACK, 504}
        )
        self.pin = pin
        return result

    async def async_set_device_name(self, name: str) -> dict[str, Any]:
        result = await self._async_set(
            encode_connect_device_name(name),
            "device_name",
            expected_cmd={CONNECT_RESPONSE_ACK, 502},
        )
        self.name = name.strip()
        return result

    async def async_sync_time(self, value: datetime) -> dict[str, Any]:
        return await self._async_set(encode_connect_time(value), "time")

    async def async_set_wifi(self, ssid: str, password: str) -> dict[str, Any]:
        return await self._async_set(encode_connect_wifi(ssid, password), "wifi")

    async def async_set_led(self, **settings: Any) -> dict[str, Any]:
        return await self._async_set(encode_connect_led(**settings), "led")

    async def async_set_multi_area(self, **settings: Any) -> dict[str, Any]:
        return await self._async_set(encode_connect_multi_area(**settings), "multi_area")

    async def async_set_schedule(self, schedule: dict[str, Any]) -> dict[str, Any]:
        return await self._async_set(encode_connect_schedule(schedule), "schedule")

    async def async_set_schedule_paused(self, paused: bool) -> dict[str, Any]:
        return await self._async_set(encode_connect_schedule_pause(paused), "schedule_pause")

    async def async_send_connect_json(self, message: dict[str, Any]) -> dict[str, Any]:
        """Send an advanced raw JSON command without interpreting its schema."""
        if "cmd" not in message:
            raise GrouwBleError("Connect payload must contain cmd")
        return await self.async_request_connect(
            encode_connect_message(message),
            expected_cmd=None,
            command_name="raw_connect",
            mutation=message.get("cmd") == 0,
        )

    async def async_send_raw_json(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Send an advanced raw Connect JSON command."""
        return await self.async_send_connect_json(payload)
