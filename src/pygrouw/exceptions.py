"""Exceptions raised by pyGrouw."""
from __future__ import annotations


class GrouwBleError(Exception):
    """Base BLE communication error."""


class GrouwBleDeviceNotFound(GrouwBleError):
    """Raised when no connectable BLE device is available for the address."""


class GrouwBleTimeout(GrouwBleError):
    """Raised when a BLE request times out."""


class GrouwBleConnectionError(GrouwBleError):
    """Raised when BLE connection fails."""


class GrouwBleGattError(GrouwBleError):
    """Raised on GATT write/notify failure."""


class GrouwBleAuthenticationError(GrouwBleError):
    """Raised when mower PIN authentication fails."""
