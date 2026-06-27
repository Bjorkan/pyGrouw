"""Python BLE library for Grouw robotic mowers."""
from __future__ import annotations

from .client import GrouwBleMowerClient
from .discovery import (
    DiscoveredMower,
    discover_devices,
    find_device_by_address,
    has_supported_service_uuid,
    is_supported_advertisement,
    is_supported_bluetooth_name,
    is_valid_pin,
    normalize_address,
)
from .exceptions import (
    GrouwBleAuthenticationError,
    GrouwBleConnectionError,
    GrouwBleDeviceNotFound,
    GrouwBleError,
    GrouwBleGattError,
    GrouwBleTimeout,
)
from .mower import GrouwMower
from .protocol import (
    MowerState,
    encode_bluekey_command,
    encode_bluekey_payload,
    encode_daye_command,
    encode_daye_session_start,
    encode_raw_payload,
    parse_daye_payload,
    redact_daye_message,
    state_from_message,
)

__all__ = [
    "GrouwBleAuthenticationError",
    "GrouwBleConnectionError",
    "GrouwBleDeviceNotFound",
    "GrouwBleError",
    "GrouwBleGattError",
    "GrouwBleMowerClient",
    "GrouwBleTimeout",
    "GrouwMower",
    "DiscoveredMower",
    "MowerState",
    "discover_devices",
    "encode_bluekey_command",
    "encode_bluekey_payload",
    "encode_daye_command",
    "encode_daye_session_start",
    "encode_raw_payload",
    "find_device_by_address",
    "has_supported_service_uuid",
    "is_supported_advertisement",
    "is_supported_bluetooth_name",
    "is_valid_pin",
    "normalize_address",
    "parse_daye_payload",
    "redact_daye_message",
    "state_from_message",
]
