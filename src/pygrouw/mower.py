"""High-level mower data model."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

from .client import GrouwBleMowerClient
from .const import DEFAULT_NAME
from .protocol import MowerState, state_from_message


class GrouwMower:
    """Stateful mower model backed by a Grouw BLE client."""

    def __init__(
        self,
        client: GrouwBleMowerClient,
        *,
        state: MowerState | None = None,
    ) -> None:
        self.client = client
        self.state = state or MowerState(
            address=client.address,
            name=client.name or DEFAULT_NAME,
        )

    @property
    def address(self) -> str:
        """Return the mower BLE address."""
        return self.state.address

    @property
    def name(self) -> str | None:
        """Return the mower name."""
        return self.state.name

    @property
    def battery_level(self) -> int | None:
        """Return the last known battery level."""
        return self.state.battery_level

    @property
    def mode(self) -> int | None:
        """Return the last known raw Daye mode byte."""
        return self.state.mode

    @property
    def station(self) -> bool | None:
        """Return whether the mower last reported being in the station."""
        return self.state.station

    async def async_update(self) -> MowerState:
        """Poll the mower and update local state."""
        message = await self.client.async_get_all_info()
        self.state = state_from_message(self.client.address, message, self.state)
        return self.state

    async def async_update_device_information(self) -> MowerState:
        """Read the mower's standard GATT identity and revision fields."""
        information = await self.client.async_get_device_information()
        self.state = replace(
            self.state,
            model=information.get("model", self.state.model),
            serial=information.get("serial", self.state.serial),
            firmware_version=information.get("firmware_version", self.state.firmware_version),
            last_communication=datetime.now(UTC),
        )
        return self.state

    async def async_command(self, command: str, *, point: int | None = None) -> MowerState:
        """Send a mower command and update local state from the response."""
        if point is None:
            message = await self.client.async_command(command)
        else:
            message = await self.client.async_command(command, point=point)
        self.state = state_from_message(self.client.address, message, self.state)
        return self.state

    async def async_start(self) -> MowerState:
        """Start mowing from the charging station."""
        return await self.async_command("start")

    async def async_resume(self) -> MowerState:
        """Resume mowing while away from the charging station."""
        return await self.async_command("resume")

    async def async_pause(self) -> MowerState:
        """Pause mowing."""
        return await self.async_command("pause")

    async def async_dock(self) -> MowerState:
        """Return the mower to the charging station."""
        return await self.async_command("dock")

    async def async_trim(self) -> MowerState:
        """Start the Connect-generation edge-trimming mode."""
        return await self.async_command("trim")

    async def async_start_at_point(self, point: int) -> MowerState:
        """Start a Connect-generation mower at a configured start point."""
        return await self.async_command("start_point", point=point)

    async def async_manual_forward(self) -> MowerState:
        """Drive a DYM-generation mower forward in manual mode."""
        return await self.async_command("manual_forward")

    async def async_manual_reverse(self) -> MowerState:
        """Drive a DYM-generation mower backward in manual mode."""
        return await self.async_command("manual_reverse")

    async def async_manual_left(self) -> MowerState:
        """Turn a DYM-generation mower left in manual mode."""
        return await self.async_command("manual_left")

    async def async_manual_right(self) -> MowerState:
        """Turn a DYM-generation mower right in manual mode."""
        return await self.async_command("manual_right")

    async def async_manual_stop(self) -> MowerState:
        """Stop DYM manual driving."""
        return await self.async_command("manual_stop")

    async def async_start_blade(self) -> MowerState:
        """Start the DYM cutting blade in manual mode."""
        return await self.async_command("blade_start")

    async def async_stop_blade(self) -> MowerState:
        """Stop the DYM cutting blade in manual mode."""
        return await self.async_command("blade_stop")

    async def async_force_stop(self) -> MowerState:
        """Send the DYM force-stop command."""
        return await self.async_command("force_stop")

    async def async_send_raw_json(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Send a raw debug payload and update state when status fields exist."""
        message = await self.client.async_send_raw_json(payload)
        self.state = state_from_message(self.client.address, message, self.state)
        return message
