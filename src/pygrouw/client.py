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
    DAYE_RESPONSE_PIN_CHANGE,
    DAYE_RESPONSE_PIN_OR_AUTH,
    DAYE_RESPONSE_STATUS,
    encode_daye_change_pin,
    encode_daye_command,
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
        expected_cmd: int | None,
        timeout: float,
        phase: str,
    ) -> dict[str, Any]:
        """Wait for a parsed notification with the expected command byte."""
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
            if expected_cmd is None or cmd == expected_cmd:
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
    ) -> dict[str, Any]:
        """Serialize and send a Daye DYM payload."""
        async with self._request_lock:
            return await self._async_request_daye_locked(
                payload,
                follow_up_status=follow_up_status,
                authenticate=authenticate,
                expected_cmd=expected_cmd,
                timeout=timeout,
                command_name=command_name,
            )

    async def _async_request_daye_locked(
        self,
        payload: bytes,
        follow_up_status: bool = False,
        authenticate: bool = True,
        expected_cmd: int | None = DAYE_RESPONSE_STATUS,
        timeout: float = DEFAULT_BLE_TIMEOUT,
        command_name: str = "raw",
    ) -> dict[str, Any]:
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
        auth_response = await self.async_request_daye(
            encode_daye_command("auth_query"),
            authenticate=True,
            expected_cmd=DAYE_RESPONSE_PIN_OR_AUTH,
            command_name="change_pin_verify",
        )
        if auth_response.get("mower_pin") == new_pin:
            self.pin = new_pin
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
