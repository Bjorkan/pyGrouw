"""Tests for the high-level mower model."""
from __future__ import annotations

import asyncio
from typing import Any

from pygrouw.mower import GrouwMower
from pygrouw.protocol import MowerState


class _Client:
    address = "AA:BB:CC:DD:EE:FF"
    name = "Test mower"

    def __init__(self) -> None:
        self.commands: list[str] = []
        self.raw_payloads: list[dict[str, Any]] = []

    async def async_get_all_info(self) -> dict[str, Any]:
        return {
            "cmd": 0x80,
            "battery_level": 75,
            "mode": 0x14,
            "station": True,
        }

    async def async_command(self, command: str) -> dict[str, Any]:
        self.commands.append(command)
        return {
            "cmd": 0x80,
            "battery_level": 60,
            "mode": 0x00,
            "station": False,
        }

    async def async_send_raw_json(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.raw_payloads.append(payload)
        return {
            "cmd": 0x80,
            "battery_level": payload["battery_level"],
        }


def test_mower_initial_state_uses_client_identity() -> None:
    """The model exposes a stable initial state from the client."""
    mower = GrouwMower(_Client())  # type: ignore[arg-type]

    assert mower.state == MowerState(
        address="AA:BB:CC:DD:EE:FF",
        name="Test mower",
    )
    assert mower.address == "AA:BB:CC:DD:EE:FF"
    assert mower.name == "Test mower"
    assert mower.battery_level is None


def test_mower_update_polls_client_and_updates_state() -> None:
    """Polling maps the raw response into a MowerState object."""

    async def run() -> None:
        mower = GrouwMower(_Client())  # type: ignore[arg-type]

        state = await mower.async_update()

        assert state is mower.state
        assert mower.battery_level == 75
        assert mower.mode == 0x14
        assert mower.station is True
        assert state.last_seen is not None

    asyncio.run(run())


def test_mower_command_helpers_update_state() -> None:
    """Command helpers delegate to the BLE client command names."""

    async def run() -> None:
        client = _Client()
        mower = GrouwMower(client)  # type: ignore[arg-type]

        await mower.async_start()
        await mower.async_resume()
        await mower.async_pause()
        state = await mower.async_dock()

        assert client.commands == ["start", "resume", "pause", "dock"]
        assert state is mower.state
        assert mower.battery_level == 60
        assert mower.mode == 0x00
        assert mower.station is False

    asyncio.run(run())


def test_mower_raw_payload_updates_state_when_status_fields_exist() -> None:
    """Raw debug responses still feed the data model state."""

    async def run() -> None:
        client = _Client()
        mower = GrouwMower(client)  # type: ignore[arg-type]

        message = await mower.async_send_raw_json({"battery_level": 42})

        assert message["battery_level"] == 42
        assert client.raw_payloads == [{"battery_level": 42}]
        assert mower.battery_level == 42

    asyncio.run(run())
