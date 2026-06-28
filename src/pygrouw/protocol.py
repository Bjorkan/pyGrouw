"""BLE framing and parsing for Grouw mower devices."""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
import logging
from typing import Any, Iterable

_LOGGER = logging.getLogger(__name__)

DYM_PREFIX = b"DYM"
DYM_TRAILER = bytes.fromhex("160601ff0a")
DYM_NOTIFICATION_TRAILER = bytes.fromhex("160601")
DYM_STATUS_NOTIFICATION_LENGTH = 22
PIN_LENGTH = 4
BLUEKEY_PREFIX = bytes((0x88, 0xB2, 0x9A))
BLUEKEY_LENGTH = 48
BLUEKEY_TRAILER_VALUES = (44, 12, 2, 510, 20)
BLUEKEY_TRAILER_START = 19

DAYE_STATUS_REQUEST = bytes.fromhex(
    "44594d00111111111111111100000000000000160601ff0a"
)
DAYE_START_MOWING = bytes.fromhex(
    "44594d01020000000000000000000000000000160601ff0a"
)
DAYE_RESUME_MOWING = bytes.fromhex(
    "44594d01000000000000000000000000000000160601ff0a"
)
DAYE_PAUSE_MOWING = bytes.fromhex(
    "44594d01010000000000000000000000000000160601ff0a"
)
DAYE_DOCK = bytes.fromhex("44594d01030000000000000000000000000000160601ff0a")
DAYE_AUTH_QUERY = bytes.fromhex("44594d0c000000000000000000000000000000160601ff0a")

DAYE_CHANGE_PIN = 0x06
DAYE_RESPONSE_PIN_CHANGE = 0x86
DAYE_MULTI_AREA_WRITE = 0x0D
DAYE_MULTI_AREA_QUERY = 0x1D
DAYE_RESPONSE_MULTI_AREA = 0x8D
DAYE_RESPONSE_PIN_OR_AUTH = 0x8C

DAYE_MULTI_AREA_QUERY_PAYLOAD = bytes.fromhex("44594d1d000000000000000000000000000000160601ff0a")
DAYE_MOWER_SETTINGS_WRITE = 0x09
DAYE_MOWER_SETTINGS_QUERY = 0x19
DAYE_RESPONSE_MOWER_SETTINGS = 0x89

DAYE_MOWER_SETTINGS_QUERY_PAYLOAD = bytes.fromhex("44594d19000000000000000000000000000000160601ff0a")
DAYE_RESPONSE_STATUS = 0x80

BLUEKEY_QUERY_INFO = 0x00
BLUEKEY_SET_TIME = 0x04
BLUEKEY_CHANGE_PIN = 0x0C
BLUEKEY_MOWER_SETTING_WRITE = 0x12
BLUEKEY_QUERY_PIN = 0x18
BLUEKEY_WORK_TIME = 0x28
BLUEKEY_MOWER_SETTING_QUERY = 0x32
BLUEKEY_MULTI_AREA_QUERY = 0x3A
BLUEKEY_ERROR_MEMORY = 0x3C

BLUEKEY_COMMAND_SPECS: dict[str, tuple[int, tuple[int, ...]]] = {
    "query_info": (BLUEKEY_QUERY_INFO, (0x22,) * 8),
    "set_time": (BLUEKEY_SET_TIME, (0x28,)),
    "query_pin": (BLUEKEY_QUERY_PIN, ()),
    "work_time": (BLUEKEY_WORK_TIME, ()),
    "mower_settings": (BLUEKEY_MOWER_SETTING_QUERY, ()),
    "mower_setting_query": (BLUEKEY_MOWER_SETTING_QUERY, ()),
    "multi_area": (BLUEKEY_MULTI_AREA_QUERY, ()),
    "multi_area_query": (BLUEKEY_MULTI_AREA_QUERY, ()),
    "error_memory": (BLUEKEY_ERROR_MEMORY, ()),
    "start": (0x00, ()),
    "stop": (0x02, ()),
    "go_to_work": (0x04, ()),
    "back_to_station": (0x06, ()),
}

BLUEKEY_SUB_COMMAND_NAMES: dict[int, str] = {
    BLUEKEY_QUERY_INFO: "query_info",
    BLUEKEY_SET_TIME: "set_time",
    BLUEKEY_CHANGE_PIN: "change_pin",
    BLUEKEY_MOWER_SETTING_WRITE: "mower_setting_write",
    BLUEKEY_QUERY_PIN: "query_pin",
    BLUEKEY_WORK_TIME: "work_time",
    BLUEKEY_MOWER_SETTING_QUERY: "mower_settings",
    BLUEKEY_MULTI_AREA_QUERY: "multi_area",
    BLUEKEY_ERROR_MEMORY: "error_memory",
}


def _looks_like_pin_digits(payload: bytes) -> bool:
    """Return true when payload bytes look like the app's numeric PIN digits."""
    return len(payload) == PIN_LENGTH and all(0 <= byte <= 9 for byte in payload)


def _coerce_int(value: Any, name: str) -> int:
    """Coerce a decimal or 0x-prefixed integer field."""
    try:
        return int(value, 0) if isinstance(value, str) else int(value)
    except (TypeError, ValueError) as err:
        raise ValueError(f"{name} must be an integer") from err


def _coerce_byte(value: Any, name: str) -> int:
    """Coerce and validate a byte-sized integer field."""
    byte = _coerce_int(value, name)
    if not 0 <= byte <= 0xFF:
        raise ValueError(f"{name} must be between 0 and 255")
    return byte


def _normalize_bluekey_command_name(command: str) -> str:
    """Normalize debug command aliases for BlueKey payload construction."""
    normalized = command.strip().lower().replace("-", "_").replace(" ", "_")
    if normalized.startswith("bluekey:"):
        normalized = normalized.removeprefix("bluekey:")
    if normalized.startswith("bluekey_"):
        normalized = normalized.removeprefix("bluekey_")
    return normalized


def _coerce_bluekey_data(data: Any) -> tuple[int, ...]:
    """Coerce debug BlueKey data bytes from JSON-friendly shapes."""
    if data is None:
        return ()
    if isinstance(data, str):
        return tuple(bytes.fromhex(data.replace(" ", "")))
    if not isinstance(data, Iterable):
        raise ValueError("bluekey_data must be a byte list or hex string")
    return tuple(_coerce_byte(value, "bluekey_data") for value in data)


def _bluekey_wire_byte(value: int) -> int:
    """Convert APK List<int> values to bytes for debug writes."""
    return value & 0xFF


def daye_ten_to_hex(value: str | int) -> int:
    """Mirror the APK Helper.tenToHex conversion."""
    decimal_value = int(str(value))
    hex_text = format(decimal_value, "x")
    return int(hex_text, 32)


def encode_bluekey_payload(sub_cmd: int, data: Iterable[int] = ()) -> bytes:
    """Build a 48-byte BlueKey payload from the APK-observed layout."""
    if not 0 <= sub_cmd <= 0xFF:
        raise ValueError("bluekey_sub_cmd must be between 0 and 255")
    data_values = tuple(data)
    if len(data_values) > 15:
        raise ValueError("bluekey_data may contain at most 15 bytes")

    values = [0] * BLUEKEY_LENGTH
    values[0:4] = [*BLUEKEY_PREFIX, sub_cmd]
    values[4 : 4 + len(data_values)] = data_values
    values[
        BLUEKEY_TRAILER_START : BLUEKEY_TRAILER_START
        + len(BLUEKEY_TRAILER_VALUES)
    ] = BLUEKEY_TRAILER_VALUES
    return bytes(_bluekey_wire_byte(value) for value in values)


def encode_bluekey_command(command: str) -> bytes:
    """Encode a named BlueKey debug command from APK page logic."""
    normalized = _normalize_bluekey_command_name(command)
    spec = BLUEKEY_COMMAND_SPECS.get(normalized)
    if spec is None:
        raise ValueError(f"Unsupported BlueKey command: {command}")
    sub_cmd, data = spec
    return encode_bluekey_payload(sub_cmd, data)


def redact_daye_message(message: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of a parsed message with user-sensitive fields redacted."""
    redacted = dict(message)
    if "mower_pin" in redacted:
        redacted["mower_pin"] = "****"
    raw_hex = redacted.get("raw_hex")
    if isinstance(raw_hex, str) and "mower_pin" in message and len(raw_hex) >= 16:
        # Bytes 4..7 are the PIN digits when a response exposes them.
        redacted["raw_hex"] = f"{raw_hex[:8]}********{raw_hex[16:]}"
    if isinstance(raw_hex, str) and message.get("cmd") == DAYE_CHANGE_PIN and len(raw_hex) >= 24:
        # Bytes 4..11 contain old and new PIN digits.
        redacted["raw_hex"] = f"{raw_hex[:8]}****************{raw_hex[24:]}"
    return redacted


def encode_daye_session_start(now: datetime | None = None) -> bytes:
    """Return the Daye session/time payload sent after a fresh connection."""
    current = now or datetime.now()
    return b"".join(
        (
            DYM_PREFIX,
            bytes(
                (
                    0x02,
                    0x14,
                    current.year % 100,
                    current.month,
                    current.day,
                    current.hour,
                    current.minute,
                )
            ),
            b"\x00" * 9,
            DYM_TRAILER,
        )
    )


def encode_daye_command(command: str) -> bytes:
    """Return a Daye command payload captured from the official app."""
    if command == "status":
        return DAYE_STATUS_REQUEST
    if command == "start":
        return DAYE_START_MOWING
    if command == "resume":
        return DAYE_RESUME_MOWING
    if command == "pause":
        return DAYE_PAUSE_MOWING
    if command == "dock":
        return DAYE_DOCK
    if command == "auth_query":
        return DAYE_AUTH_QUERY
    if command == "session_start":
        return encode_daye_session_start()
    raise ValueError(f"Unsupported Daye command: {command}")


def _encode_daye_pin_digits(pin: str) -> bytes:
    """Encode a 4-digit PIN string into four binary digit bytes."""
    if len(pin) != 4 or not pin.isdecimal():
        raise ValueError("PIN must be exactly 4 decimal digits")
    return bytes(int(ch) for ch in pin)


def encode_daye_change_pin(old_pin: str, new_pin: str) -> bytes:
    """Build a 24-byte DYM PIN change payload (command 0x06)."""
    return b"".join(
        (
            DYM_PREFIX,
            bytes((DAYE_CHANGE_PIN,)),
            _encode_daye_pin_digits(old_pin),
            _encode_daye_pin_digits(new_pin),
            b"\x00" * 7,
            DYM_TRAILER,
        )
    )


def encode_daye_multi_area(
    area2_percentage: int,
    area2_distance: int,
    area3_percentage: int,
    area3_distance: int,
) -> bytes:
    """Build a 24-byte DYM multi-area write payload (command 0x0d)."""
    if not 0 <= area2_percentage <= 100:
        raise ValueError("area2_percentage must be between 0 and 100")
    if not 0 <= area3_percentage <= 100:
        raise ValueError("area3_percentage must be between 0 and 100")
    if not 0 <= area2_distance <= 999:
        raise ValueError("area2_distance must be between 0 and 999")
    if not 0 <= area3_distance <= 999:
        raise ValueError("area3_distance must be between 0 and 999")

    def _decimal_chunks(value: int) -> tuple[int, int, int]:
        hundreds = value // 100
        tens = (value // 10) % 10
        ones = value % 10
        return (hundreds, tens, ones)

    return b"".join(
        (
            DYM_PREFIX,
            bytes((DAYE_MULTI_AREA_WRITE,)),
            bytes((area2_percentage,)),
            bytes(_decimal_chunks(area2_distance)),
            bytes((area3_percentage,)),
            bytes(_decimal_chunks(area3_distance)),
            b"\x00" * 7,
            DYM_TRAILER,
        )
    )


def encode_daye_mower_settings(
    mow_in_rain: bool,
    boundary_cut: bool,
    helix: bool,
    rain_delay_hours: int,
    rain_delay_minutes: int,
    *,
    unknown_setting: bool = False,
) -> bytes:
    """Build a 24-byte DYM mower settings write payload (command 0x09)."""
    if not 0 <= rain_delay_hours <= 23:
        raise ValueError("rain_delay_hours must be between 0 and 23")
    if not 0 <= rain_delay_minutes <= 59:
        raise ValueError("rain_delay_minutes must be between 0 and 59")

    return b"".join(
        (
            DYM_PREFIX,
            bytes((DAYE_MOWER_SETTINGS_WRITE,)),
            bytes(
                (
                    int(mow_in_rain),
                    int(boundary_cut),
                    int(unknown_setting),
                    int(helix),
                    rain_delay_hours,
                    rain_delay_minutes,
                )
            ),
            b"\x00" * 9,
            DYM_TRAILER,
        )
    )


def encode_raw_payload(payload: dict[str, Any]) -> bytes:
    """Encode a raw debug payload for the Daye BLE characteristic."""
    raw_hex = payload.get("raw_hex")
    if raw_hex is not None:
        return bytes.fromhex(str(raw_hex).replace(" ", ""))

    bluekey = payload.get("bluekey")
    if bluekey is not None:
        return encode_bluekey_command(str(bluekey))

    bluekey_sub_cmd = payload.get("bluekey_sub_cmd")
    if bluekey_sub_cmd is not None:
        return encode_bluekey_payload(
            _coerce_byte(bluekey_sub_cmd, "bluekey_sub_cmd"),
            _coerce_bluekey_data(payload.get("bluekey_data", payload.get("data"))),
        )

    command = payload.get("command")
    if command is not None:
        command_name = str(command)
        raw_command_name = command_name.strip().lower().replace("-", "_")
        if raw_command_name.startswith(("bluekey:", "bluekey_")):
            return encode_bluekey_command(command_name)
        return encode_daye_command(command_name)

    raise ValueError("Payload must contain raw_hex or command")


def _bluekey_bool(payload: bytes, index: int) -> bool | None:
    """Return the app's settings boolean interpretation for a response byte."""
    if len(payload) <= index:
        return None
    return payload[index] == 1


def _bluekey_decimal_chunks(chunks: bytes) -> str | None:
    """Assemble the APK's variable-width decimal distance display chunks."""
    if not chunks:
        return None
    significant = [str(value) for value in chunks if value > 0]
    return "".join(significant) if significant else "0"


def _parse_bluekey_payload(
    payload: bytes,
    bluekey_context: str | None = None,
) -> dict[str, Any] | None:
    """Parse a BlueKey notification into APK-style byte keys."""
    if not payload.startswith(BLUEKEY_PREFIX):
        return None

    sub_cmd = payload[3] if len(payload) > 3 else None
    context = (
        _normalize_bluekey_command_name(bluekey_context)
        if bluekey_context
        else None
    )
    command_name = context or (
        BLUEKEY_SUB_COMMAND_NAMES.get(sub_cmd) if sub_cmd is not None else None
    )
    message: dict[str, Any] = {
        "protocol": "bluekey",
        "raw_hex": payload.hex(),
        "cmd": sub_cmd,
        "bluekey_sub_cmd": sub_cmd,
    }
    if command_name is not None:
        message["bluekey_command"] = command_name
    for index, value in enumerate(payload, start=1):
        message[f"byte{index}"] = str(value)
    if len(payload) >= BLUEKEY_TRAILER_START + len(BLUEKEY_TRAILER_VALUES):
        message["bluekey_trailer_hex"] = payload[
            BLUEKEY_TRAILER_START : BLUEKEY_TRAILER_START
            + len(BLUEKEY_TRAILER_VALUES)
        ].hex()

    if command_name == "query_pin" and len(payload) >= 8:
        pin_bytes = payload[4:8]
        if _looks_like_pin_digits(pin_bytes):
            message["mower_pin"] = "".join(str(byte) for byte in pin_bytes)

    if command_name == "change_pin" and len(payload) >= 5:
        message["pin_change_success"] = payload[4] == 0

    if command_name == "query_info" and len(payload) >= 13:
        message["bluekey_battery_level"] = payload[4]
        message["bluekey_work_mode"] = payload[12]
        message["bluekey_work_mode_hex"] = f"0x{daye_ten_to_hex(payload[12]):02x}"

    if command_name in {"mower_settings", "mower_setting_query"} and len(payload) >= 12:
        message["mower_settings"] = {
            "mow_in_rain": _bluekey_bool(payload, 4),
            "boundary_cut": _bluekey_bool(payload, 5),
            "ultrasound": _bluekey_bool(payload, 6),
            "helix": _bluekey_bool(payload, 7),
            "rain_delay_hour": payload[8] if len(payload) > 8 else None,
            "rain_delay_minute": payload[9] if len(payload) > 9 else None,
            "led": _bluekey_bool(payload, 11),
        }

    if command_name in {"multi_area", "multi_area_query"} and len(payload) >= 12:
        message["multi_area"] = {
            "area2_percentage": payload[4],
            "area2_distance": _bluekey_decimal_chunks(payload[5:8]),
            "area3_percentage": payload[8],
            "area3_distance": _bluekey_decimal_chunks(payload[9:12]),
        }

    if command_name == "work_time" and len(payload) >= 19:
        mode = daye_ten_to_hex(payload[3])
        days = (
            "monday",
            "tuesday",
            "wednesday",
            "thursday",
            "friday",
            "saturday",
            "sunday",
        )
        message["work_time_mode"] = f"0x{mode:02x}"
        message["work_time_delimiter"] = "." if mode == 0x85 else ":"
        message["work_time"] = {
            day: {
                "primary": payload[4 + index],
                "secondary": payload[11 + index],
            }
            for index, day in enumerate(days)
        }

    return message


def parse_daye_payload(
    payload: bytes,
    bluekey_context: str | None = None,
) -> dict[str, Any] | None:
    """Parse a Daye DYM notification payload."""
    if not payload:
        return None
    bluekey_message = _parse_bluekey_payload(payload, bluekey_context)
    if bluekey_message is not None:
        return bluekey_message
    if not payload.startswith(DYM_PREFIX):
        _LOGGER.debug("Ignoring non-Daye BLE payload: %s", payload.hex())
        return None

    message: dict[str, Any] = {
        "raw_hex": payload.hex(),
        "cmd": payload[3] if len(payload) > 3 else None,
    }
    if payload.endswith(DYM_NOTIFICATION_TRAILER):
        message["trailer"] = payload[-3:].hex()

    # Status notifications captured from the official app are 22 bytes.
    if (
        len(payload) == DYM_STATUS_NOTIFICATION_LENGTH
        and payload[3] == DAYE_RESPONSE_STATUS
        and payload.endswith(DYM_NOTIFICATION_TRAILER)
    ):
        message["battery_level"] = payload[4]
        message["mode"] = payload[12]
        if payload[7] in (0x00, 0x01):
            message["station"] = payload[7] == 0x01
    elif len(payload) >= 8 and payload[3] == DAYE_RESPONSE_PIN_OR_AUTH:
        pin_bytes = payload[4:8]
        if _looks_like_pin_digits(pin_bytes):
            message["mower_pin"] = "".join(str(byte) for byte in pin_bytes)
    elif len(payload) >= 8 and payload[3] == DAYE_RESPONSE_PIN_CHANGE:
        message["pin_change_ack"] = True
        message["pin_change_success"] = payload[4:19] == b"\x00" * 15
    elif len(payload) >= 12 and payload[3] == DAYE_RESPONSE_MULTI_AREA:
        distance2 = payload[5] * 100 + payload[6] * 10 + payload[7]
        distance3 = payload[9] * 100 + payload[10] * 10 + payload[11]
        message["multi_area"] = {
            "area2_percentage": payload[4],
            "area2_distance": distance2,
            "area3_percentage": payload[8],
            "area3_distance": distance3,
        }
    elif len(payload) >= 12 and payload[3] == DAYE_RESPONSE_MOWER_SETTINGS:
        message["mower_settings"] = {
            "mow_in_rain": payload[4] == 1,
            "boundary_cut": payload[5] == 1,
            "unknown_setting": payload[6] == 1,
            "helix": payload[7] == 1,
            "rain_delay_hour": payload[8],
            "rain_delay_minute": payload[9],
            "led": payload[11] == 1,
        }
    return message


def _optional_int(data: dict[str, Any], key: str) -> int | None:
    value = data.get(key)
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


@dataclass(slots=True, frozen=True)
class MowerState:
    """Latest parsed mower state."""

    address: str
    name: str | None = None
    model: str | None = None
    serial: str | None = None
    firmware_version: str | None = None
    battery_level: int | None = None
    mode: int | None = None
    station: bool | None = None
    last_response_cmd: int | None = None
    raw: dict[str, Any] | None = None
    last_seen: datetime | None = None

    @property
    def available(self) -> bool:
        return self.last_seen is not None


def state_from_message(
    address: str,
    message: dict[str, Any],
    previous: MowerState | None = None,
) -> MowerState:
    """Update a state object from a parsed Daye BLE message."""
    base = previous or MowerState(address=address)
    cmd = _optional_int(message, "cmd")
    updates: dict[str, Any] = {
        "raw": redact_daye_message(message),
        "last_response_cmd": cmd,
        "last_seen": datetime.now(timezone.utc),
    }

    for src, dst in (
        ("battery_level", "battery_level"),
        ("mode", "mode"),
    ):
        value = _optional_int(message, src)
        if value is not None:
            updates[dst] = value

    station = message.get("station")
    if isinstance(station, bool):
        updates["station"] = station

    return replace(base, **updates)
