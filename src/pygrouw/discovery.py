"""BLE discovery helpers for Grouw mower devices."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from bleak import BleakScanner
from bleak.backends.device import BLEDevice

from .const import DAYE_SERVICE_UUIDS, DEFAULT_NAME, SUPPORTED_LOCAL_NAME_PREFIXES


@dataclass(slots=True, frozen=True)
class DiscoveredMower:
    """A supported mower found during BLE discovery."""

    device: BLEDevice
    address: str
    name: str
    service_uuids: tuple[str, ...] = ()
    rssi: int | None = None


def normalize_address(address: str) -> str:
    """Normalize a BLE address for lookup and comparison."""
    return address.strip().upper()


def is_valid_pin(pin: str) -> bool:
    """Return true for the Daye app's required 4-digit PIN shape."""
    return len(pin) == 4 and pin.isascii() and pin.isdecimal()


def is_supported_bluetooth_name(name: str) -> bool:
    """Return true for BLE local names used by supported mower apps/devices."""
    return name.startswith(SUPPORTED_LOCAL_NAME_PREFIXES)


def has_supported_service_uuid(service_uuids: list[str] | tuple[str, ...]) -> bool:
    """Return true if a discovery includes a confirmed Daye mower service UUID."""
    supported = {uuid.lower() for uuid in DAYE_SERVICE_UUIDS}
    return any(uuid.lower() in supported for uuid in service_uuids)


def is_supported_advertisement(
    name: str | None,
    service_uuids: list[str] | tuple[str, ...] = (),
) -> bool:
    """Return true for supported Daye mower Bluetooth discoveries."""
    return is_supported_bluetooth_name(name or "") or has_supported_service_uuid(
        service_uuids
    )


def _metadata_service_uuids(device: BLEDevice) -> tuple[str, ...]:
    metadata = getattr(device, "metadata", None)
    if not isinstance(metadata, dict):
        return ()
    uuids = metadata.get("uuids") or metadata.get("service_uuids") or ()
    return tuple(str(uuid) for uuid in uuids)


def _advertisement_service_uuids(advertisement: Any | None) -> tuple[str, ...]:
    uuids = getattr(advertisement, "service_uuids", ()) if advertisement else ()
    return tuple(str(uuid) for uuid in (uuids or ()))


def _advertisement_name(advertisement: Any | None) -> str | None:
    if advertisement is None:
        return None
    return getattr(advertisement, "local_name", None)


def _advertisement_rssi(advertisement: Any | None) -> int | None:
    if advertisement is None:
        return None
    rssi = getattr(advertisement, "rssi", None)
    return int(rssi) if rssi is not None else None


def _discovered_mower(
    device: BLEDevice,
    advertisement: Any | None = None,
) -> DiscoveredMower | None:
    service_uuids = _advertisement_service_uuids(advertisement)
    if not service_uuids:
        service_uuids = _metadata_service_uuids(device)
    name = getattr(device, "name", None) or _advertisement_name(advertisement) or ""

    if not is_supported_advertisement(name, service_uuids):
        return None

    return DiscoveredMower(
        device=device,
        address=normalize_address(str(getattr(device, "address"))),
        name=name or DEFAULT_NAME,
        service_uuids=service_uuids,
        rssi=_advertisement_rssi(advertisement),
    )


async def discover_devices(
    timeout: float = 5.0,
    *,
    scanner: type[BleakScanner] = BleakScanner,
) -> list[DiscoveredMower]:
    """Scan for supported Grouw/Daye BLE mower devices."""
    try:
        discoveries = await scanner.discover(timeout=timeout, return_adv=True)
    except TypeError:
        discoveries = await scanner.discover(timeout=timeout)

    devices: list[DiscoveredMower] = []
    if isinstance(discoveries, dict):
        iterable = discoveries.values()
        for entry in iterable:
            device, advertisement = entry
            if mower := _discovered_mower(device, advertisement):
                devices.append(mower)
        return devices

    for device in discoveries:
        if mower := _discovered_mower(device):
            devices.append(mower)
    return devices


async def find_device_by_address(
    address: str,
    timeout: float = 5.0,
    *,
    scanner: type[BleakScanner] = BleakScanner,
    supported_only: bool = False,
) -> BLEDevice | None:
    """Scan for and return a connectable BLEDevice by address."""
    target = normalize_address(address)

    if supported_only:
        for mower in await discover_devices(timeout=timeout, scanner=scanner):
            if mower.address == target:
                return mower.device
        return None

    discoveries = await scanner.discover(timeout=timeout)
    for device in discoveries:
        if normalize_address(str(getattr(device, "address"))) == target:
            return device
    return None
