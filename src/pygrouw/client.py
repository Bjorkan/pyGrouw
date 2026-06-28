"""BLE client for Grouw mower devices."""
from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
import inspect
import logging
from typing import Any, TypeAlias

from bleak import BleakClient, BleakError
from bleak.backends.device import BLEDevice
from bleak_retry_connector import establish_connection

from .const import (
    DEFAULT_BLE_TIMEOUT,
    DEFAULT_CHUNK_DELAY,
    DEFAULT_NAME,
    DEFAULT_REQUESTED_MTU,
    READ_CHARACTERISTIC_UUID,
    WRITE_CHARACTERISTIC_UUID,
)
from .exceptions import (
    GrouwBleAuthenticationError,
    GrouwBleConnectionError,
    GrouwBleDeviceNotFound,
    GrouwBleError,
    GrouwBleGattError,
    GrouwBleTimeout,
)
from .protocol import (
    BLUEKEY_PREFIX,
    DAYE_CHANGE_PIN,
    DAYE_MULTI_AREA_QUERY_PAYLOAD,
    DAYE_RESPONSE_MULTI_AREA,
    DAYE_MOWER_SETTINGS_QUERY_PAYLOAD,
    DAYE_RESPONSE_MOWER_SETTINGS,
    DAYE_RESPONSE_PIN_CHANGE,
    DAYE_RESPONSE_PIN_OR_AUTH,
    DAYE_RESPONSE_STATUS,
    encode_daye_change_pin,
    encode_daye_command,
    encode_daye_multi_area,
    encode_daye_mower_settings,
    encode_daye_session_start,
    encode_raw_payload,
    parse_daye_payload,
    redact_daye_message,
)

_LOGGER = logging.getLogger(__name__)

BLE_BACKEND_EXCEPTIONS = (BleakError, TimeoutError, OSError)
DeviceProvider: TypeAlias = Callable[[], BLEDevice | None | Awaitable[BLEDevice | None]]


def _drain_queue(queue: asyncio.Queue[Any]) -> None:
    """Discard all items currently in the queue."""
    while not queue.empty():
        try:
            queue.get_nowait()
        except asyncio.QueueEmpty:
            break


def _coerce_bool(value: Any) -> bool:
    """Coerce common service payload boolean shapes."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
        raise GrouwBleError("authenticate must be a boolean value")
    return bool(value)


def _coerce_expected_cmd(value: Any) -> int | None:
    """Coerce a raw service expected command byte."""
    if value is None:
        return None
    try:
        command = int(value, 0) if isinstance(value, str) else int(value)
    except (TypeError, ValueError) as err:
        raise GrouwBleError(
            "expect_cmd must be an integer command byte or null"
        ) from err
    if not 0 <= command <= 0xFF:
        raise GrouwBleError("expect_cmd must be between 0 and 255")
    return command


class GrouwBleMowerClient:
    """Small serialized BLE client for a single mower.

    The client intentionally does not scan. Applications should resolve a
    connectable BLEDevice with their own Bluetooth manager and pass it through
    ``device`` or ``device_provider``.
    """

    def __init__(
        self,
        address: str,
        name: str | None = None,
        pin: str = "",
        *,
        device: BLEDevice | None = None,
        device_provider: DeviceProvider | None = None,
    ) -> None:
        self.address = address.upper()
        self.name = name or DEFAULT_NAME
        self.pin = pin.strip()
        self._device = device
        self._device_provider = device_provider
        self._tx_counter = 0
        self._tx_id = 0
        self._request_lock = asyncio.Lock()

    async def _resolve_device(self) -> BLEDevice | None:
        """Return the current connectable BLEDevice."""
        if self._device_provider is None:
            return self._device
        result = self._device_provider()
        if inspect.isawaitable(result):
            return await result
        return result

    @classmethod
    async def from_discovery(
        cls,
        address: str,
        name: str | None = None,
        pin: str = "",
        *,
        timeout: float = 5.0,
    ) -> GrouwBleMowerClient:
        """Create a client by scanning for a connectable BLE device."""
        from .discovery import find_device_by_address, normalize_address

        normalized_address = normalize_address(address)
        device = await find_device_by_address(normalized_address, timeout=timeout)
        device_name = name or getattr(device, "name", None) or DEFAULT_NAME
        return cls(
            normalized_address,
            device_name,
            pin,
            device=device,
        )

    async def _write_with_log(
        self,
        client: BleakClient,
        payload: bytes,
        label: str,
    ) -> None:
        """Write to GATT characteristic and log the result."""
        try:
            await client.write_gatt_char(
                WRITE_CHARACTERISTIC_UUID, payload, response=True
            )
            _LOGGER.debug(
                "[%s tx=%s] write %s ok payload=%s",
                self.address, self._tx_id, label, payload.hex()
            )
        except BLE_BACKEND_EXCEPTIONS as err:
            _LOGGER.error(
                "[%s tx=%s] write %s failed: %s (errno=%s)",
                self.address, self._tx_id, label, err,
                getattr(err, "args", ("unknown",))
            )
            raise GrouwBleGattError(
                f"GATT write failed for {label} on {self.address}: {err}"
            ) from err

    async def _request_mtu_with_log(self, client: BleakClient) -> None:
        """Best-effort MTU request matching the official app connection flow."""
        request_mtu = getattr(client, "request_mtu", None)
        current_mtu = getattr(client, "mtu_size", "unknown")
        if request_mtu is None:
            _LOGGER.debug(
                "[%s tx=%s] MTU request unsupported (current_mtu=%s)",
                self.address, self._tx_id, current_mtu
            )
            return

        try:
            result = request_mtu(DEFAULT_REQUESTED_MTU)
            if inspect.isawaitable(result):
                result = await result
        except Exception as err:  # noqa: BLE001 - MTU support is backend-specific
            _LOGGER.debug(
                "[%s tx=%s] MTU request skipped: %s (current_mtu=%s)",
                self.address, self._tx_id, err, current_mtu
            )
            return

        _LOGGER.debug(
            "[%s tx=%s] MTU request ok requested=%s result=%s current_mtu=%s",
            self.address, self._tx_id, DEFAULT_REQUESTED_MTU, result,
            getattr(client, "mtu_size", "unknown")
        )

    async def _wait_for_response(
        self,
        queue: asyncio.Queue[dict[str, Any]],
        expected_cmd: int | set[int] | None,
        timeout: float,
        phase: str,
    ) -> dict[str, Any]:
        """Wait for a parsed notification matching the expected command(s)."""
        deadline = asyncio.get_running_loop().time() + timeout
        while True:
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                _LOGGER.error(
                    "[%s tx=%s] notification timeout in %s (expected_cmd=%s)",
                    self.address, self._tx_id, phase, expected_cmd
                )
                raise GrouwBleTimeout(
                    f"Timeout waiting for notification from {self.address}"
                )
            try:
                message = await asyncio.wait_for(queue.get(), timeout=remaining)
            except asyncio.TimeoutError as err:
                _LOGGER.error(
                    "[%s tx=%s] notification timeout in %s (expected_cmd=%s)",
                    self.address, self._tx_id, phase, expected_cmd
                )
                raise GrouwBleTimeout(
                    f"Timeout waiting for notification from {self.address}"
                ) from err

            cmd = message.get("cmd")
            if expected_cmd is None:
                return message
            if isinstance(expected_cmd, set):
                if cmd in expected_cmd:
                    _LOGGER.debug(
                        "[%s tx=%s] selected %s response cmd=%s raw=%s",
                        self.address, self._tx_id, phase, cmd,
                        redact_daye_message(message).get("raw_hex", "?")
                    )
                    return message
            elif cmd == expected_cmd:
                _LOGGER.debug(
                    "[%s tx=%s] selected %s response cmd=%s raw=%s",
                    self.address, self._tx_id, phase, cmd,
                    redact_daye_message(message).get("raw_hex", "?")
                )
                return message

            _LOGGER.debug(
                "[%s tx=%s] ignoring notification cmd=%s in %s (waiting for %s)",
                self.address, self._tx_id, cmd, phase, expected_cmd
            )

    def _verify_auth_response(self, message: dict[str, Any]) -> None:
        """Verify the configured PIN against the mower auth/PIN response."""
        if not self.pin:
            raise GrouwBleAuthenticationError("A 4-digit mower PIN is required")

        mower_pin = message.get("mower_pin")
        if mower_pin is None:
            raise GrouwBleError(
                "Mower auth response did not include PIN data; cannot verify configured PIN"
            )

        if str(mower_pin) != self.pin:
            raise GrouwBleAuthenticationError(
                "Configured mower PIN does not match the mower auth response"
            )

        _LOGGER.debug(
            "[%s tx=%s] configured PIN verified against mower auth response",
            self.address, self._tx_id
        )

    async def async_request_daye(
        self,
        payload: bytes,
        follow_up_status: bool = False,
        authenticate: bool = True,
        expected_cmd: int | None = DAYE_RESPONSE_STATUS,
        timeout: float = DEFAULT_BLE_TIMEOUT,
        command_name: str = "raw",
        write_only: bool = False,
    ) -> dict[str, Any] | None:
        """Serialize and send a Daye DYM payload."""
        async with self._request_lock:
            return await self._async_request_daye_locked(
                payload,
                follow_up_status=follow_up_status,
                authenticate=authenticate,
                expected_cmd=expected_cmd,
                timeout=timeout,
                command_name=command_name,
                write_only=write_only,
            )

    async def _async_request_daye_locked(
        self,
        payload: bytes,
        follow_up_status: bool = False,
        authenticate: bool = True,
        expected_cmd: int | None = DAYE_RESPONSE_STATUS,
        timeout: float = DEFAULT_BLE_TIMEOUT,
        command_name: str = "raw",
        write_only: bool = False,
    ) -> dict[str, Any] | None:
        """Send a Daye DYM payload and wait for the first parsed notification."""
        self._tx_counter += 1
        self._tx_id = self._tx_counter

        _LOGGER.debug(
            "[%s tx=%s] request starting command=%s follow_up=%s authenticate=%s",
            self.address, self._tx_id, command_name, follow_up_status, authenticate
        )

        ble_device = await self._resolve_device()
        if ble_device is None:
            _LOGGER.error(
                "[%s tx=%s] no connectable BLE device found",
                self.address, self._tx_id
            )
            raise GrouwBleDeviceNotFound(
                f"No connectable Bluetooth device found for {self.address}"
            )

        _LOGGER.debug("[%s tx=%s] BLE device resolved", self.address, self._tx_id)

        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        loop = asyncio.get_running_loop()

        def _notification_handler(_sender: int | str, data: bytearray) -> None:
            message = parse_daye_payload(bytes(data), bluekey_context=command_name)
            if message is not None:
                _LOGGER.debug(
                    "[%s tx=%s] notify raw=%s",
                    self.address, self._tx_id,
                    redact_daye_message(message).get("raw_hex", data.hex())
                )
                loop.call_soon_threadsafe(queue.put_nowait, message)

        client: BleakClient | None = None
        notify_started = False
        try:
            _LOGGER.debug(
                "[%s tx=%s] connecting (timeout=%s)",
                self.address, self._tx_id, timeout
            )
            try:
                client = await establish_connection(
                    BleakClient,
                    ble_device,
                    self.name,
                    max_attempts=3,
                    timeout=timeout,
                )
            except BLE_BACKEND_EXCEPTIONS as err:
                _LOGGER.error(
                    "[%s tx=%s] connect failed: %s",
                    self.address, self._tx_id, err
                )
                raise GrouwBleConnectionError(
                    f"BLE connect failed for {self.address}: {err}"
                ) from err

            await self._request_mtu_with_log(client)

            _LOGGER.debug(
                "[%s tx=%s] connected, starting notify",
                self.address, self._tx_id
            )
            try:
                await client.start_notify(
                    READ_CHARACTERISTIC_UUID, _notification_handler
                )
            except BLE_BACKEND_EXCEPTIONS as err:
                _LOGGER.error(
                    "[%s tx=%s] start_notify failed: %s",
                    self.address, self._tx_id, err
                )
                raise GrouwBleGattError(
                    f"GATT start_notify failed on {self.address}: {err}"
                ) from err
            notify_started = True

            _LOGGER.debug("[%s tx=%s] notify started", self.address, self._tx_id)

            if authenticate:
                await self._write_with_log(
                    client, encode_daye_session_start(), "session_start"
                )
                await asyncio.sleep(DEFAULT_CHUNK_DELAY)
                await self._write_with_log(
                    client, encode_daye_command("auth_query"), "auth_query"
                )
                auth_message = await self._wait_for_response(
                    queue,
                    DAYE_RESPONSE_PIN_OR_AUTH,
                    timeout,
                    "auth",
                )
                self._verify_auth_response(auth_message)

                _drain_queue(queue)
                _LOGGER.debug(
                    "[%s tx=%s] queue drained after auth",
                    self.address, self._tx_id
                )

            await self._write_with_log(client, payload, "command")
            if follow_up_status:
                await asyncio.sleep(DEFAULT_CHUNK_DELAY)
                _drain_queue(queue)
                _LOGGER.debug(
                    "[%s tx=%s] queue drained before follow-up status",
                    self.address, self._tx_id
                )
                await self._write_with_log(
                    client, encode_daye_command("status"), "follow_up_status"
                )

            if write_only:
                return None

            return await self._wait_for_response(
                queue,
                expected_cmd,
                timeout,
                "command",
            )

        except (
            GrouwBleAuthenticationError,
            GrouwBleConnectionError,
            GrouwBleGattError,
            GrouwBleTimeout,
        ):
            raise
        except BLE_BACKEND_EXCEPTIONS as err:
            _LOGGER.error(
                "[%s tx=%s] unexpected BLE backend error: %s",
                self.address, self._tx_id, err
            )
            raise GrouwBleError(
                f"Unexpected BLE error on {self.address}: {err}"
            ) from err
        finally:
            if client is not None:
                if notify_started:
                    try:
                        await client.stop_notify(READ_CHARACTERISTIC_UUID)
                    except Exception:  # noqa: BLE001 - cleanup must be best effort
                        pass
                try:
                    await client.disconnect()
                except Exception:  # noqa: BLE001
                    pass
                _LOGGER.debug("[%s tx=%s] disconnected", self.address, self._tx_id)

    async def async_get_all_info(self) -> dict[str, Any]:
        """Request the Daye status packet without the audible auth prelude."""
        return await self.async_request_daye(
            encode_daye_command("status"),
            authenticate=False,
            command_name="status",
        )

    async def async_command(self, command: str) -> dict[str, Any]:
        """Send a quiet Daye mower command and refresh status."""
        return await self.async_request_daye(
            encode_daye_command(command),
            authenticate=False,
            follow_up_status=True,
            command_name=command,
        )

    async def async_change_pin(
        self,
        new_pin: str,
        old_pin: str | None = None,
    ) -> dict[str, Any]:
        """Change the mower PIN via DYM command 0x06 and verify with auth query."""
        old = old_pin or self.pin
        payload = encode_daye_change_pin(old, new_pin)
        response = await self.async_request_daye(
            payload,
            authenticate=True,
            expected_cmd=DAYE_RESPONSE_PIN_CHANGE,
            command_name="change_pin",
        )
        if not response.get("pin_change_success"):
            raise GrouwBleError("PIN change was not acknowledged as successful")

        auth_response = await self.async_request_daye(
            encode_daye_command("auth_query"),
            authenticate=False,
            expected_cmd=DAYE_RESPONSE_PIN_OR_AUTH,
            command_name="change_pin_verify",
        )
        if auth_response.get("mower_pin") != new_pin:
            raise GrouwBleError("PIN change verification failed")

        self.pin = new_pin
        return response

    async def _async_request_daye_multi_locked(
        self,
        steps: list[tuple[bytes, int | None | set[int], float, str, int]],
        authenticate: bool = True,
        timeout: float = DEFAULT_BLE_TIMEOUT,
    ) -> list[Any]:
        """Execute multiple DYM payload writes in a single BLE session.

        Each step is (payload, expected_cmd, delay, command_name, collect_count).
        expected_cmd can be int, set[int], or None.
        collect_count=0 means write-only (no response expected).
        collect_count=1 means wait for one response matching expected_cmd.
        collect_count=N means wait for N responses (each must match expected_cmd
        when it is an int/set, or accept any cmd when None).
        """
        self._tx_counter += 1
        self._tx_id = self._tx_counter

        ble_device = await self._resolve_device()
        if ble_device is None:
            raise GrouwBleDeviceNotFound(
                f"No connectable Bluetooth device found for {self.address}"
            )

        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        loop = asyncio.get_running_loop()

        def _notification_handler(_sender: int | str, data: bytearray) -> None:
            message = parse_daye_payload(bytes(data))
            if message is not None:
                loop.call_soon_threadsafe(queue.put_nowait, message)

        client: BleakClient | None = None
        notify_started = False
        responses: list[Any] = []
        try:
            client = await establish_connection(
                BleakClient, ble_device, self.name, max_attempts=3, timeout=timeout,
            )
            await self._request_mtu_with_log(client)
            await client.start_notify(READ_CHARACTERISTIC_UUID, _notification_handler)
            notify_started = True

            if authenticate:
                await self._write_with_log(client, encode_daye_session_start(), "session_start")
                await asyncio.sleep(DEFAULT_CHUNK_DELAY)
                await self._write_with_log(client, encode_daye_command("auth_query"), "auth_query")
                auth_message = await self._wait_for_response(
                    queue, DAYE_RESPONSE_PIN_OR_AUTH, timeout, "auth",
                )
                self._verify_auth_response(auth_message)
                _drain_queue(queue)

            for payload, expected_cmd, delay, command_name, collect_count in steps:
                if delay > 0:
                    await asyncio.sleep(delay)
                await self._write_with_log(client, payload, command_name)
                if collect_count > 0:
                    collected: list[dict[str, Any]] = []
                    for _ in range(collect_count):
                        response = await self._wait_for_response(
                            queue, expected_cmd, timeout, command_name,
                        )
                        collected.append(response)
                    responses.append(collected if collect_count > 1 else collected[0])
                else:
                    responses.append(None)

            return responses

        except (GrouwBleAuthenticationError, GrouwBleConnectionError, GrouwBleGattError, GrouwBleTimeout):
            raise
        except BLE_BACKEND_EXCEPTIONS as err:
            raise GrouwBleError(f"Unexpected BLE error on {self.address}: {err}") from err
        finally:
            if client is not None:
                if notify_started:
                    try:
                        await client.stop_notify(READ_CHARACTERISTIC_UUID)
                    except Exception:
                        pass
                try:
                    await client.disconnect()
                except Exception:
                    pass

    async def async_get_multi_area(self) -> dict[str, Any]:
        """Query the mower multi-area settings via DYM 0x1d."""
        async with self._request_lock:
            return await self._async_request_daye_locked(
                DAYE_MULTI_AREA_QUERY_PAYLOAD,
                authenticate=True,
                expected_cmd=DAYE_RESPONSE_MULTI_AREA,
                command_name="multi_area_query",
            )

    async def async_set_multi_area(
        self,
        area2_percentage: int,
        area2_distance: int,
        area3_percentage: int,
        area3_distance: int,
    ) -> dict[str, Any]:
        """Write multi-area settings, verify with query, and return query response."""
        from .exceptions import GrouwBleError

        async with self._request_lock:
            result = await self._async_request_daye_multi_locked(
                [
                    (encode_daye_multi_area(
                        area2_percentage=area2_percentage,
                        area2_distance=area2_distance,
                        area3_percentage=area3_percentage,
                        area3_distance=area3_distance,
                    ), None, DEFAULT_CHUNK_DELAY, "multi_area_write", 0),
                    (DAYE_MULTI_AREA_QUERY_PAYLOAD, DAYE_RESPONSE_MULTI_AREA, DEFAULT_CHUNK_DELAY, "multi_area_verify", 1),
                ],
                authenticate=True,
            )
            response = result[1]
            if isinstance(response, dict):
                multi = response.get("multi_area", {})
                expected = {
                    "area2_percentage": area2_percentage,
                    "area2_distance": area2_distance,
                    "area3_percentage": area3_percentage,
                    "area3_distance": area3_distance,
                }
                if multi != expected:
                    raise GrouwBleError("Multi-area verification failed")
            return response

    async def async_get_mower_settings(self) -> dict[str, Any]:
        """Query the mower settings via DYM 0x19."""
        async with self._request_lock:
            return await self._async_request_daye_locked(
                DAYE_MOWER_SETTINGS_QUERY_PAYLOAD,
                authenticate=True,
                expected_cmd=DAYE_RESPONSE_MOWER_SETTINGS,
                command_name="mower_settings_query",
            )

    async def async_set_mower_settings(
        self,
        *,
        mow_in_rain: bool,
        boundary_cut: bool,
        helix: bool,
        rain_delay_hours: int,
        rain_delay_minutes: int,
        unknown_setting: bool = False,
    ) -> dict[str, Any]:
        """Write mower settings via DYM 0x09 and verify with a follow-up query."""
        from .exceptions import GrouwBleError

        async with self._request_lock:
            result = await self._async_request_daye_multi_locked(
                [
                    (encode_daye_mower_settings(
                        mow_in_rain=mow_in_rain,
                        boundary_cut=boundary_cut,
                        helix=helix,
                        rain_delay_hours=rain_delay_hours,
                        rain_delay_minutes=rain_delay_minutes,
                        unknown_setting=unknown_setting,
                    ), None, DEFAULT_CHUNK_DELAY, "mower_settings_write", 0),
                    (DAYE_MOWER_SETTINGS_QUERY_PAYLOAD, DAYE_RESPONSE_MOWER_SETTINGS, DEFAULT_CHUNK_DELAY, "mower_settings_verify", 1),
                ],
                authenticate=True,
            )
            response = result[1]
            if isinstance(response, dict):
                settings = response.get("mower_settings", {})
                expected = {
                    "mow_in_rain": mow_in_rain,
                    "boundary_cut": boundary_cut,
                    "unknown_setting": unknown_setting,
                    "helix": helix,
                    "rain_delay_hour": rain_delay_hours,
                    "rain_delay_minute": rain_delay_minutes,
                }
                for key, value in expected.items():
                    if settings.get(key) != value:
                        raise GrouwBleError("Mower settings verification failed")
            return response

    async def async_send_raw_json(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Send a raw debug payload and return the first parsed notification."""
        try:
            raw_payload = encode_raw_payload(payload)
        except ValueError as err:
            raise GrouwBleError(str(err)) from err
        is_bluekey = raw_payload.startswith(BLUEKEY_PREFIX)
        expected = payload.get("expect_cmd", None if is_bluekey else DAYE_RESPONSE_STATUS)
        expected_cmd = _coerce_expected_cmd(expected)
        authenticate = _coerce_bool(payload.get("authenticate", True))
        command_name = str(
            payload.get("command")
            or payload.get("bluekey")
            or payload.get("bluekey_context")
            or ("bluekey_raw" if is_bluekey else "raw")
        )
        return await self.async_request_daye(
            raw_payload,
            authenticate=authenticate,
            expected_cmd=expected_cmd,
            command_name=command_name,
        )
