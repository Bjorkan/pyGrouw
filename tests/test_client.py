"""Tests for Grouw BLE client helpers."""
from __future__ import annotations

import asyncio

import pytest

from pygrouw.client import (
    GrouwBleAuthenticationError,
    GrouwBleConnectionError,
    GrouwBleError,
    GrouwBleGattError,
    GrouwBleMowerClient,
    GrouwBleTimeout,
    _coerce_bool,
    _coerce_expected_cmd,
    _drain_queue,
)
from pygrouw.protocol import (
    DAYE_RESPONSE_PIN_OR_AUTH,
    encode_bluekey_command,
    encode_daye_command,
)
from pygrouw.const import DEFAULT_REQUESTED_MTU


def test_drain_queue_discards_stale_notifications() -> None:
    """Queued notifications can be discarded at request phase boundaries."""
    queue: asyncio.Queue[dict[str, int]] = asyncio.Queue()
    queue.put_nowait({"cmd": 0x80})
    queue.put_nowait({"cmd": 0x8C})

    _drain_queue(queue)

    assert queue.empty()


def test_coerce_bool_accepts_common_service_payload_strings() -> None:
    """Raw service boolean options may arrive as strings."""
    assert _coerce_bool(True)
    assert _coerce_bool("true")
    assert not _coerce_bool(False)
    assert not _coerce_bool("false")
    assert not _coerce_bool("0")
    assert _coerce_bool("yes")
    assert not _coerce_bool("off")
    with pytest.raises(GrouwBleError, match="authenticate"):
        _coerce_bool("flase")


def test_coerce_expected_cmd_accepts_hex_strings_and_validates_range() -> None:
    """Raw service expected command options are parsed as command bytes."""
    assert _coerce_expected_cmd(None) is None
    assert _coerce_expected_cmd("0x80") == 0x80
    assert _coerce_expected_cmd("128") == 128
    assert _coerce_expected_cmd(0x8C) == 0x8C

    with pytest.raises(GrouwBleError, match="between 0 and 255"):
        _coerce_expected_cmd("0x100")
    with pytest.raises(GrouwBleError, match="integer command byte"):
        _coerce_expected_cmd("eighty")


def test_wait_for_response_skips_unexpected_notifications() -> None:
    """The BLE client waits for the expected DYM command byte."""

    async def run() -> None:
        client = GrouwBleMowerClient(
            "AA:BB:CC:DD:EE:FF", "Test mower"
        )
        client._tx_id = 1
        queue: asyncio.Queue[dict[str, int]] = asyncio.Queue()
        queue.put_nowait({"cmd": 0x80})
        queue.put_nowait({"cmd": DAYE_RESPONSE_PIN_OR_AUTH})

        message = await client._wait_for_response(
            queue,
            DAYE_RESPONSE_PIN_OR_AUTH,
            0.1,
            "auth",
        )

        assert message == {"cmd": DAYE_RESPONSE_PIN_OR_AUTH}

    asyncio.run(run())


def test_wait_for_response_uses_single_deadline() -> None:
    """Unexpected notifications must not extend the overall response timeout."""

    async def run() -> None:
        client = GrouwBleMowerClient(
            "AA:BB:CC:DD:EE:FF", "Test mower"
        )
        client._tx_id = 1
        queue: asyncio.Queue[dict[str, int]] = asyncio.Queue()

        async def put_unexpected_notifications() -> None:
            for _ in range(3):
                await asyncio.sleep(0.04)
                queue.put_nowait({"cmd": 0x80})

        producer = asyncio.create_task(put_unexpected_notifications())
        start = asyncio.get_running_loop().time()
        with pytest.raises(GrouwBleTimeout):
            await client._wait_for_response(
                queue,
                DAYE_RESPONSE_PIN_OR_AUTH,
                0.08,
                "auth",
            )
        elapsed = asyncio.get_running_loop().time() - start
        producer.cancel()

        assert elapsed < 0.13

    asyncio.run(run())


def test_write_with_log_maps_backend_timeout_to_gatt_error() -> None:
    """Backend write timeouts are surfaced as GATT failures."""

    class _Client:
        async def write_gatt_char(
            self, _uuid: str, _payload: bytes, *, response: bool
        ) -> None:
            raise TimeoutError("write timed out")

    async def run() -> None:
        client = GrouwBleMowerClient(
            "AA:BB:CC:DD:EE:FF", "Test mower"
        )
        client._tx_id = 1

        with pytest.raises(GrouwBleGattError, match="GATT write failed"):
            await client._write_with_log(  # type: ignore[arg-type]
                _Client(), b"DYM", "command"
            )

    asyncio.run(run())


def test_connect_timeout_is_classified_as_connection_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Connection backend timeouts should not be reported as unknown BLE errors."""

    async def run() -> None:
        import pygrouw.client as ble_client

        async def fail_connect(*args: object, **kwargs: object) -> object:
            raise TimeoutError("connect timed out")

        monkeypatch.setattr(ble_client, "establish_connection", fail_connect)
        client = GrouwBleMowerClient(
            "AA:BB:CC:DD:EE:FF", "Test mower", device_provider=lambda: object()
        )

        with pytest.raises(GrouwBleConnectionError, match="connect timed out"):
            await client.async_get_all_info()

    asyncio.run(run())


def test_client_requests_are_serialized() -> None:
    """Direct BLE client requests cannot overlap for the same client."""

    async def run() -> None:
        client = GrouwBleMowerClient(
            "AA:BB:CC:DD:EE:FF", "Test mower"
        )

        class Tracker:
            active = 0
            max_active = 0

        async def fake_locked_request(
            payload: bytes,
            *,
            follow_up_status: bool = False,
            authenticate: bool = True,
            expected_cmd: int | None = None,
            timeout: float = 0,
            command_name: str = "raw",
            write_only: bool = False,
        ) -> dict[str, int] | None:
            Tracker.active += 1
            Tracker.max_active = max(Tracker.max_active, Tracker.active)
            await asyncio.sleep(0)
            Tracker.active -= 1
            return {"cmd": payload[0]}

        client._async_request_daye_locked = (  # type: ignore[method-assign]
            fake_locked_request
        )

        results = await asyncio.gather(
            client.async_request_daye(b"\x80"),
            client.async_request_daye(b"\x8c"),
        )

        assert Tracker.max_active == 1
        assert results == [{"cmd": 0x80}, {"cmd": 0x8C}]

    asyncio.run(run())


def test_verify_auth_response_accepts_matching_configured_pin() -> None:
    """A configured PIN is checked against the mower auth response."""
    client = GrouwBleMowerClient(
        "AA:BB:CC:DD:EE:FF", "Test mower", pin="1234"
    )
    client._tx_id = 1

    client._verify_auth_response({"cmd": DAYE_RESPONSE_PIN_OR_AUTH, "mower_pin": "1234"})


def test_status_poll_skips_auth_prelude_to_avoid_beep() -> None:
    """Normal status polling uses the quiet unauthenticated DYM status request."""

    async def run() -> None:
        client = GrouwBleMowerClient(
            "AA:BB:CC:DD:EE:FF", "Test mower", pin="1234"
        )
        seen: dict[str, object] = {}

        async def fake_request(
            payload: bytes,
            *,
            authenticate: bool = True,
            command_name: str = "raw",
            **kwargs: object,
        ) -> dict[str, int]:
            seen["payload"] = payload
            seen["authenticate"] = authenticate
            seen["command_name"] = command_name
            return {"cmd": 0x80}

        client.async_request_daye = fake_request  # type: ignore[method-assign]

        await client.async_get_all_info()

        assert seen == {
            "payload": encode_daye_command("status"),
            "authenticate": False,
            "command_name": "status",
        }

    asyncio.run(run())


def test_missing_device_provider_raises_device_not_found() -> None:
    """The library does not scan when no BLEDevice has been injected."""

    async def run() -> None:
        client = GrouwBleMowerClient("AA:BB:CC:DD:EE:FF", "Test mower")

        from pygrouw.client import GrouwBleDeviceNotFound

        with pytest.raises(GrouwBleDeviceNotFound, match="No connectable"):
            await client.async_get_all_info()

    asyncio.run(run())


def test_commands_skip_auth_prelude_and_follow_up_with_status() -> None:
    """Control commands skip the audible auth prelude and then poll status."""

    async def run() -> None:
        client = GrouwBleMowerClient(
            "AA:BB:CC:DD:EE:FF", "Test mower", pin="1234"
        )
        seen: dict[str, object] = {}

        async def fake_request(
            payload: bytes,
            *,
            authenticate: bool = True,
            follow_up_status: bool = False,
            command_name: str = "raw",
            **kwargs: object,
        ) -> dict[str, int]:
            seen["payload"] = payload
            seen["authenticate"] = authenticate
            seen["follow_up_status"] = follow_up_status
            seen["command_name"] = command_name
            return {"cmd": 0x80}

        client.async_request_daye = fake_request  # type: ignore[method-assign]

        await client.async_command("dock")

        assert seen == {
            "payload": encode_daye_command("dock"),
            "authenticate": False,
            "follow_up_status": True,
            "command_name": "dock",
        }

    asyncio.run(run())


def test_verify_auth_response_requires_configured_pin() -> None:
    """Authenticated requests require a configured mower PIN."""
    client = GrouwBleMowerClient(
        "AA:BB:CC:DD:EE:FF", "Test mower", pin=""
    )
    client._tx_id = 1

    with pytest.raises(GrouwBleAuthenticationError, match="PIN is required"):
        client._verify_auth_response(
            {"cmd": DAYE_RESPONSE_PIN_OR_AUTH, "mower_pin": "1234"}
        )


def test_verify_auth_response_rejects_mismatched_configured_pin() -> None:
    """A wrong configured PIN fails before command payloads are sent."""
    client = GrouwBleMowerClient(
        "AA:BB:CC:DD:EE:FF", "Test mower", pin="9999"
    )
    client._tx_id = 1

    with pytest.raises(GrouwBleAuthenticationError, match="does not match"):
        client._verify_auth_response(
            {"cmd": DAYE_RESPONSE_PIN_OR_AUTH, "mower_pin": "1234"}
        )


def test_verify_auth_response_requires_pin_data_when_pin_is_configured() -> None:
    """Missing auth PIN data is a protocol/read issue, not a proven PIN mismatch."""
    client = GrouwBleMowerClient(
        "AA:BB:CC:DD:EE:FF", "Test mower", pin="1234"
    )
    client._tx_id = 1

    with pytest.raises(GrouwBleError, match="did not include PIN") as exc_info:
        client._verify_auth_response({"cmd": DAYE_RESPONSE_PIN_OR_AUTH})

    assert not isinstance(exc_info.value, GrouwBleAuthenticationError)


def test_request_mtu_with_log_calls_supported_client() -> None:
    """The client requests the APK-observed MTU when the backend exposes it."""

    class _Client:
        mtu_size = 23

        def __init__(self) -> None:
            self.requested: list[int] = []

        async def request_mtu(self, mtu: int) -> int:
            self.requested.append(mtu)
            self.mtu_size = mtu
            return mtu

    async def run() -> None:
        client = GrouwBleMowerClient(
                "AA:BB:CC:DD:EE:FF", "Test mower"
        )
        client._tx_id = 1
        ble_client = _Client()

        await client._request_mtu_with_log(ble_client)  # type: ignore[arg-type]

        assert ble_client.requested == [DEFAULT_REQUESTED_MTU]
        assert ble_client.mtu_size == DEFAULT_REQUESTED_MTU

    asyncio.run(run())


def test_request_mtu_with_log_ignores_unsupported_client() -> None:
    """MTU negotiation is optional because Bleak backends differ."""

    class _Client:
        mtu_size = 23

    async def run() -> None:
        client = GrouwBleMowerClient(
                "AA:BB:CC:DD:EE:FF", "Test mower"
        )
        client._tx_id = 1

        await client._request_mtu_with_log(_Client())  # type: ignore[arg-type]

    asyncio.run(run())


def test_raw_payload_accepts_hex_expected_command_and_string_auth_flag() -> None:
    """Raw service options support hex command strings and string booleans."""

    async def run() -> None:
        client = GrouwBleMowerClient(
                "AA:BB:CC:DD:EE:FF", "Test mower"
        )
        seen: dict[str, object] = {}

        async def fake_request(
            payload: bytes,
            *,
            authenticate: bool = True,
            expected_cmd: int | None = None,
            **kwargs: object,
        ) -> dict[str, int]:
            seen["payload"] = payload
            seen["authenticate"] = authenticate
            seen["expected_cmd"] = expected_cmd
            return {"cmd": 0x80}

        client.async_request_daye = fake_request  # type: ignore[method-assign]

        await client.async_send_raw_json(
            {
                "raw_hex": "44594d",
                "authenticate": "false",
                "expect_cmd": "0x80",
            }
        )

        assert seen == {
            "payload": b"DYM",
            "authenticate": False,
            "expected_cmd": 0x80,
        }

    asyncio.run(run())


def test_raw_payload_bluekey_defaults_to_any_parsed_response() -> None:
    """BlueKey probes do not default to the DYM status response command."""

    async def run() -> None:
        client = GrouwBleMowerClient(
                "AA:BB:CC:DD:EE:FF", "Test mower"
        )
        seen: dict[str, object] = {}

        async def fake_request(
            payload: bytes,
            *,
            expected_cmd: int | None = 0x80,
            command_name: str = "raw",
            **kwargs: object,
        ) -> dict[str, int]:
            seen["payload"] = payload
            seen["expected_cmd"] = expected_cmd
            seen["command_name"] = command_name
            return {"cmd": 0x32}

        client.async_request_daye = fake_request  # type: ignore[method-assign]

        await client.async_send_raw_json({"bluekey": "mower_settings"})

        assert seen == {
            "payload": encode_bluekey_command("mower_settings"),
            "expected_cmd": None,
            "command_name": "mower_settings",
        }

    asyncio.run(run())
