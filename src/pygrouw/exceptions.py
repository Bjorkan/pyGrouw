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


class GrouwBleVerificationError(GrouwBleError):
    """Raised when read-back data does not match a requested write."""


class GrouwBleOperationIndeterminate(GrouwBleError):
    """Raised when a multi-step operation may already be partly applied."""

    def __init__(
        self,
        message: str,
        *,
        completed_steps: tuple[str, ...] = (),
        failed_step: str | None = None,
        write_may_have_completed: bool = False,
    ) -> None:
        super().__init__(message)
        self.completed_steps = completed_steps
        self.failed_step = failed_step
        self.write_may_have_completed = write_may_have_completed
