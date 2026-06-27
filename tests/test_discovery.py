"""Tests for BLE discovery helpers."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass

from pygrouw.const import DAYE_PRIMARY_SERVICE_UUID
from pygrouw.discovery import (
    discover_devices,
    find_device_by_address,
    has_supported_service_uuid,
    is_supported_advertisement,
    is_supported_bluetooth_name,
    is_valid_pin,
    normalize_address,
)


@dataclass
class _Device:
    address: str
    name: str | None = None
    metadata: dict[str, object] | None = None


@dataclass
class _Advertisement:
    local_name: str | None = None
    service_uuids: list[str] | None = None
    rssi: int | None = None


def test_discovery_predicates_match_home_assistant_flow() -> None:
    """The standalone library recognizes the same mower discoveries as HA."""
    assert normalize_address(" aa:bb ") == "AA:BB"
    assert is_valid_pin("1234")
    assert not is_valid_pin("123")
    assert not is_valid_pin("12a4")
    assert is_supported_bluetooth_name("Robot Mower_DYM")
    assert has_supported_service_uuid([DAYE_PRIMARY_SERVICE_UUID.upper()])
    assert is_supported_advertisement(None, [DAYE_PRIMARY_SERVICE_UUID])
    assert not is_supported_advertisement("Nearby Speaker", [])


def test_discover_devices_filters_supported_advertisements() -> None:
    """Only supported mower advertisements are returned."""

    class _Scanner:
        @staticmethod
        async def discover(*, timeout: float, return_adv: bool) -> dict[str, object]:
            assert timeout == 0.1
            assert return_adv is True
            return {
                "AA:BB": (
                    _Device("AA:BB", "Robot Mower_DYM"),
                    _Advertisement(rssi=-60),
                ),
                "CC:DD": (
                    _Device("CC:DD", "Other"),
                    _Advertisement(service_uuids=[DAYE_PRIMARY_SERVICE_UUID], rssi=-70),
                ),
                "EE:FF": (
                    _Device("EE:FF", "Other"),
                    _Advertisement(service_uuids=[]),
                ),
            }

    async def run() -> None:
        devices = await discover_devices(0.1, scanner=_Scanner)  # type: ignore[arg-type]

        assert [device.address for device in devices] == ["AA:BB", "CC:DD"]
        assert devices[0].name == "Robot Mower_DYM"
        assert devices[0].rssi == -60
        assert devices[1].service_uuids == (DAYE_PRIMARY_SERVICE_UUID,)

    asyncio.run(run())


def test_find_device_by_address_can_scan_without_supported_filter() -> None:
    """Manual setup can resolve any connectable BLEDevice by address."""
    target = _Device("aa:bb:cc:dd:ee:ff", "Robot Mower_DYM")

    class _Scanner:
        @staticmethod
        async def discover(*, timeout: float) -> list[_Device]:
            assert timeout == 0.1
            return [_Device("11:22"), target]

    async def run() -> None:
        device = await find_device_by_address(
            "AA:BB:CC:DD:EE:FF",
            0.1,
            scanner=_Scanner,  # type: ignore[arg-type]
        )

        assert device is target

    asyncio.run(run())


def test_find_device_by_address_supported_only_uses_mower_filter() -> None:
    """Supported-only lookup ignores devices that do not look like mowers."""
    mower = _Device("AA:BB", "Robot Mower_DYM")

    class _Scanner:
        @staticmethod
        async def discover(*, timeout: float, return_adv: bool) -> dict[str, object]:
            assert timeout == 0.1
            assert return_adv is True
            return {
                "AA:BB": (mower, _Advertisement()),
                "CC:DD": (_Device("CC:DD", "Speaker"), _Advertisement()),
            }

    async def run() -> None:
        assert (
            await find_device_by_address(
                "AA:BB",
                0.1,
                scanner=_Scanner,  # type: ignore[arg-type]
                supported_only=True,
            )
            is mower
        )
        assert (
            await find_device_by_address(
                "CC:DD",
                0.1,
                scanner=_Scanner,  # type: ignore[arg-type]
                supported_only=True,
            )
            is None
        )

    asyncio.run(run())
