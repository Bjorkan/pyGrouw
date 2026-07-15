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
    DAYE_RESPONSE_PIN_CHANGE,
    encode_daye_change_pin,
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


def test_verify_auth_response_pin_rejects_empty_explicit_pin() -> None:
    """Explicit empty auth pins must fail instead of falling back to client.pin."""
    client = GrouwBleMowerClient(
        "AA:BB:CC:DD:EE:FF", "Test mower", pin="1234"
    )
    client._tx_id = 1

    with pytest.raises(GrouwBleAuthenticationError, match="PIN is required"):
        client._verify_auth_response_pin(
            {"cmd": DAYE_RESPONSE_PIN_OR_AUTH, "mower_pin": "1234"},
            "",
        )


def test_change_pin_uses_old_pin_for_single_session_verification() -> None:
    """PIN changes authenticate with the old PIN and verify in the same session."""

    async def run() -> None:
        client = GrouwBleMowerClient(
            "AA:BB:CC:DD:EE:FF", "Test mower", pin="9999"
        )
        seen: dict[str, object] = {}

        async def fake_multi_request(
            steps: list[tuple[bytes, int | None | set[int], float, str, int]],
            authenticate: bool = True,
            auth_pin: str | None = None,
            **kwargs: object,
        ) -> list[dict[str, object]]:
            seen["steps"] = steps
            seen["authenticate"] = authenticate
            seen["auth_pin"] = auth_pin
            return [
                {"cmd": DAYE_RESPONSE_PIN_CHANGE, "pin_change_success": True},
                {"cmd": DAYE_RESPONSE_PIN_OR_AUTH, "mower_pin": "4321"},
            ]

        client._async_request_daye_multi_locked = (  # type: ignore[method-assign]
            fake_multi_request
        )

        response = await client.async_change_pin("4321", old_pin="1234")

        steps = seen["steps"]
        assert isinstance(steps, list)
        assert seen["authenticate"] is True
        assert seen["auth_pin"] == "1234"
        assert steps[0][0] == encode_daye_change_pin("1234", "4321")
        assert steps[0][1] == DAYE_RESPONSE_PIN_CHANGE
        assert steps[0][3] == "change_pin"
        assert steps[0][4] == 1
        assert steps[1][0] == encode_daye_command("auth_query")
        assert steps[1][1] == DAYE_RESPONSE_PIN_OR_AUTH
        assert steps[1][3] == "change_pin_verify"
        assert steps[1][4] == 1
        assert response["pin_change_success"] is True
        assert client.pin == "4321"

    asyncio.run(run())


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


def test_from_discovery_raises_when_address_is_not_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The convenience factory must not return an unusable client."""

    async def run() -> None:
        import pygrouw.discovery as discovery
        from pygrouw.client import GrouwBleDeviceNotFound

        async def find_none(*args: object, **kwargs: object) -> None:
            return None

        monkeypatch.setattr(discovery, "find_device_by_address", find_none)

        with pytest.raises(GrouwBleDeviceNotFound, match="was not discovered"):
            await GrouwBleMowerClient.from_discovery(
                "aa:bb:cc:dd:ee:ff",
                timeout=0.1,
            )

    asyncio.run(run())


def test_connection_uses_fresh_device_callback_without_forwarding_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Connector retries can refresh a synchronous provider route."""

    async def run() -> None:
        import pygrouw.client as ble_client

        first = object()
        second = object()
        devices = iter((first, second))
        seen: dict[str, object] = {}

        def provider() -> object:
            return next(devices)

        async def fake_connect(
            _client_class: object,
            initial_device: object,
            _name: str,
            **kwargs: object,
        ) -> object:
            seen["initial"] = initial_device
            seen["kwargs"] = kwargs
            callback = kwargs["ble_device_callback"]
            assert callable(callback)
            seen["retry"] = callback()
            return object()

        monkeypatch.setattr(ble_client, "establish_connection", fake_connect)
        client = GrouwBleMowerClient(
            "AA:BB:CC:DD:EE:FF",
            "Test mower",
            device_provider=provider,  # type: ignore[arg-type]
        )
        client._tx_id = 1

        connected = await client._establish_connection(0.1)

        assert connected is not None
        assert seen["initial"] is first
        assert seen["retry"] is second
        kwargs = seen["kwargs"]
        assert isinstance(kwargs, dict)
        assert kwargs["max_attempts"] == 3
        assert "timeout" not in kwargs

    asyncio.run(run())


def test_connection_deadline_bounds_connector_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The public connection timeout is an outer wall-clock deadline."""

    async def run() -> None:
        import pygrouw.client as ble_client

        async def never_connect(*args: object, **kwargs: object) -> object:
            await asyncio.sleep(1)
            return object()

        monkeypatch.setattr(ble_client, "establish_connection", never_connect)
        client = GrouwBleMowerClient(
            "AA:BB:CC:DD:EE:FF",
            "Test mower",
            device_provider=lambda: object(),
        )
        client._tx_id = 1
        start = asyncio.get_running_loop().time()

        with pytest.raises(GrouwBleConnectionError, match="connect failed"):
            await client._establish_connection(0.02)

        assert asyncio.get_running_loop().time() - start < 0.2

    asyncio.run(run())


def test_multi_step_path_preserves_connection_error_type(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Single and multi-step operations share connection error classification."""

    async def run() -> None:
        client = GrouwBleMowerClient(
            "AA:BB:CC:DD:EE:FF",
            "Test mower",
            device_provider=lambda: object(),
        )

        async def fail_connect(_timeout: float) -> object:
            raise GrouwBleConnectionError("route unavailable")

        monkeypatch.setattr(client, "_establish_connection", fail_connect)

        with pytest.raises(GrouwBleConnectionError, match="route unavailable"):
            await client._async_request_daye_multi_locked(
                [(b"DYM", None, 0, "write", 0)],
                authenticate=False,
            )

    asyncio.run(run())


def test_required_responses_ignore_duplicates_until_all_commands_arrive() -> None:
    """Schedule queries require one response of each command type."""

    async def run() -> None:
        client = GrouwBleMowerClient("AA:BB", "Test mower")
        client._tx_id = 1
        queue: asyncio.Queue[dict[str, int]] = asyncio.Queue()
        queue.put_nowait({"cmd": 0x84, "value": 1})
        queue.put_nowait({"cmd": 0x84, "value": 2})
        queue.put_nowait({"cmd": 0x85, "value": 3})

        responses = await client._wait_for_required_responses(
            queue, {0x84, 0x85}, 0.1, "work_time"
        )

        assert [response["cmd"] for response in responses] == [0x84, 0x85]
        assert responses[0]["value"] == 2

    asyncio.run(run())


def test_raw_write_only_mode_does_not_wait_for_notification() -> None:
    """No-response protocol writes have an explicit transport mode."""

    async def run() -> None:
        client = GrouwBleMowerClient("AA:BB", "Test mower")
        seen: dict[str, object] = {}

        async def fake_request(payload: bytes, **kwargs: object) -> None:
            seen["payload"] = payload
            seen.update(kwargs)
            return None

        client.async_request_daye = fake_request  # type: ignore[method-assign]
        response = await client.async_send_raw_json(
            {
                "raw_hex": "44594d04",
                "response_mode": "write_only",
                "authenticate": False,
            }
        )

        assert response is None
        assert seen["write_only"] is True
        assert seen["follow_up_status"] is False
        assert seen["expected_cmd"] is None

    asyncio.run(run())


def test_raw_response_mode_rejects_unknown_policy() -> None:
    """Raw response semantics must not be inferred from an invalid option."""

    async def run() -> None:
        client = GrouwBleMowerClient("AA:BB", "Test mower")
        with pytest.raises(GrouwBleError, match="response_mode"):
            await client.async_send_raw_json(
                {"raw_hex": "44594d04", "response_mode": "maybe"}
            )

    asyncio.run(run())


def test_command_result_marks_status_as_unconfirmed() -> None:
    """Transport success is distinct from physical action confirmation."""

    async def run() -> None:
        client = GrouwBleMowerClient("AA:BB", "Test mower")

        async def fake_request(*args: object, **kwargs: object) -> dict[str, int]:
            return {"cmd": 0x80, "mode": 0x14}

        client.async_request_daye = fake_request  # type: ignore[method-assign]
        result = await client.async_command_result("dock")

        assert result.command == "dock"
        assert result.write_completed
        assert not result.confirmed
        assert result.status["mode"] == 0x14

    asyncio.run(run())


def test_mower_settings_preserve_unknown_field_when_omitted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Partial settings updates read and preserve unknown mower fields."""

    async def run() -> None:
        client = GrouwBleMowerClient("AA:BB", "Test mower")
        seen: dict[str, object] = {}

        async def fake_get() -> dict[str, object]:
            return {"mower_settings": {"unknown_setting": True}}

        async def fake_multi(
            steps: list[tuple[bytes, int | None | set[int], float, str, int]],
            **kwargs: object,
        ) -> list[object]:
            seen["steps"] = steps
            return [None, {
                "mower_settings": {
                    "mow_in_rain": True,
                    "boundary_cut": False,
                    "unknown_setting": True,
                    "helix": False,
                    "rain_delay_hour": 1,
                    "rain_delay_minute": 2,
                }
            }]

        monkeypatch.setattr(client, "async_get_mower_settings", fake_get)
        monkeypatch.setattr(client, "_async_request_daye_multi_locked", fake_multi)

        await client.async_set_mower_settings(
            mow_in_rain=True,
            boundary_cut=False,
            helix=False,
            rain_delay_hours=1,
            rain_delay_minutes=2,
        )

        steps = seen["steps"]
        assert isinstance(steps, list)
        assert steps[0][0][6] == 1

    asyncio.run(run())


def test_multi_step_failure_after_write_is_indeterminate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A lost verification response preserves completed step metadata."""

    async def run() -> None:
        from pygrouw.client import GrouwBleOperationIndeterminate

        class _Client:
            async def start_notify(self, *args: object) -> None:
                return None

            async def stop_notify(self, *args: object) -> None:
                return None

            async def disconnect(self) -> None:
                return None

        client = GrouwBleMowerClient("AA:BB", "Test mower")
        monkeypatch.setattr(client, "_establish_connection", lambda timeout: None)

        async def fake_establish(timeout: float) -> _Client:
            return _Client()

        async def fake_write(*args: object, **kwargs: object) -> None:
            return None

        async def fail_wait(*args: object, **kwargs: object) -> dict[str, int]:
            raise GrouwBleTimeout("lost response")

        monkeypatch.setattr(client, "_establish_connection", fake_establish)
        monkeypatch.setattr(client, "_request_mtu_with_log", lambda client: _async_none())
        monkeypatch.setattr(client, "_write_with_log", fake_write)
        monkeypatch.setattr(client, "_wait_for_response", fail_wait)

        with pytest.raises(GrouwBleOperationIndeterminate) as exc_info:
            await client._async_request_daye_multi_locked(
                [(b"DYM", 0x80, 0, "settings_write", 1)],
                authenticate=False,
            )

        assert exc_info.value.completed_steps == ("settings_write",)
        assert exc_info.value.failed_step == "settings_write"

    async def _async_none() -> None:
        return None

    asyncio.run(run())
