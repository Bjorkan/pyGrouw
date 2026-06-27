"""High-level mower data model."""
from __future__ import annotations

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

    async def async_command(self, command: str) -> MowerState:
        """Send a mower command and update local state from the response."""
        message = await self.client.async_command(command)
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

    async def async_send_raw_json(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Send a raw debug payload and update state when status fields exist."""
        message = await self.client.async_send_raw_json(payload)
        self.state = state_from_message(self.client.address, message, self.state)
        return message
