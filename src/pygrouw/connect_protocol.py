"""Local BLE protocol used by the Grouw Robotic Mower Connect app."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import datetime
import json
from typing import Any

CONNECT_FRAME_MARKER = 0xA4
CONNECT_PACKET_LENGTH = 20
CONNECT_MAX_PAYLOAD = 3000

CONNECT_QUERY_ALL_INFO = 200
CONNECT_QUERY_STATUS = 201
CONNECT_QUERY_SCHEDULE = 203
CONNECT_QUERY_RAIN = 205
CONNECT_QUERY_MULTI_AREA = 207
CONNECT_QUERY_DEVICE_INFO = 208
CONNECT_QUERY_BATTERY = 212
CONNECT_QUERY_FEATURES = 214

CONNECT_SET_WORK_MODE = 101
CONNECT_SET_TIME = 102
CONNECT_SET_SCHEDULE = 103
CONNECT_VERIFY_PIN = 104
CONNECT_SET_RAIN = 105
CONNECT_SET_LANGUAGE = 106
CONNECT_SET_DEVICE_NAME = 107
CONNECT_SET_MULTI_AREA = 108
CONNECT_SET_WIFI = 109
CONNECT_SET_PIN = 110
CONNECT_START_UPDATE = 111
CONNECT_RESET_DEVICE = 112
CONNECT_SET_ULTRASONIC = 114
CONNECT_SET_LED = 115
CONNECT_SET_GPS = 116
CONNECT_RESET_MAP = 121
CONNECT_SET_SCHEDULE_PAUSE = 127

CONNECT_MUTATING_COMMANDS = frozenset(
    {
        CONNECT_SET_WORK_MODE,
        CONNECT_SET_TIME,
        CONNECT_SET_SCHEDULE,
        CONNECT_SET_RAIN,
        CONNECT_SET_LANGUAGE,
        CONNECT_SET_DEVICE_NAME,
        CONNECT_SET_MULTI_AREA,
        CONNECT_SET_WIFI,
        CONNECT_SET_PIN,
        CONNECT_START_UPDATE,
        CONNECT_RESET_DEVICE,
        CONNECT_SET_ULTRASONIC,
        CONNECT_SET_LED,
        CONNECT_SET_GPS,
        CONNECT_RESET_MAP,
        CONNECT_SET_SCHEDULE_PAUSE,
    }
)

CONNECT_RESPONSE_ACK = 400
CONNECT_RESPONSE_ALL_INFO = 500
CONNECT_RESPONSE_STATUS = 501
CONNECT_RESPONSE_SCHEDULE = 503
CONNECT_RESPONSE_RAIN = 505
CONNECT_RESPONSE_MULTI_AREA = 507
CONNECT_RESPONSE_DEVICE_INFO = 508
CONNECT_RESPONSE_BATTERY = 512
CONNECT_RESPONSE_FEATURES = 514
CONNECT_RESPONSE_RESET_MAP = 523

CONNECT_WORK_MODES = {
    "pause": 0,
    "stop": 0,
    "resume": 1,
    "start": 1,
    "work": 1,
    "dock": 2,
    "home": 2,
    "trim": 4,
    "start_point": 5,
}

CONNECT_LANGUAGES = (
    "Chinese",
    "Czech",
    "Danish",
    "Dutch",
    "English",
    "Finnish",
    "French",
    "German",
    "Hungarian",
    "Italian",
    "Japanese",
    "Norwegian",
    "Polish",
    "Portuguese",
    "Slovak",
    "Slovenian",
    "Spanish",
    "Swedish",
    "Russian",
    "Serbian",
    "Romanian",
    "Hebrew",
)


def connect_xor(data: bytes) -> int:
    """Return the XOR checksum used by the Connect app's BLE frame."""
    checksum = 0
    for value in data:
        checksum ^= value
    return checksum


def encode_connect_json(message: Mapping[str, Any]) -> bytes:
    """Serialize a mower command exactly as compact UTF-8 JSON."""
    return json.dumps(message, ensure_ascii=False, separators=(",", ":")).encode()


def frame_connect_payload(payload: bytes) -> list[bytes]:
    """Split a JSON payload into the app's A4/length/XOR BLE packets."""
    if len(payload) > CONNECT_MAX_PAYLOAD:
        raise ValueError(f"Connect payload may contain at most {CONNECT_MAX_PAYLOAD} bytes")
    header = bytes(
        (
            CONNECT_FRAME_MARKER,
            len(payload) & 0xFF,
            (len(payload) >> 8) & 0xFF,
            connect_xor(payload),
        )
    )
    framed = header + payload
    return [framed[offset : offset + CONNECT_PACKET_LENGTH] for offset in range(0, len(framed), 20)]


def encode_connect_message(message: Mapping[str, Any]) -> list[bytes]:
    """Encode and frame one Connect-generation JSON command."""
    return frame_connect_payload(encode_connect_json(message))


class ConnectFrameDecoder:
    """Incrementally reassemble A4-framed notifications."""

    def __init__(self) -> None:
        self._buffer = bytearray()

    def feed(self, data: bytes | bytearray) -> list[bytes]:
        """Consume notification bytes and return every complete valid payload."""
        self._buffer.extend(data)
        messages: list[bytes] = []
        while self._buffer:
            try:
                marker = self._buffer.index(CONNECT_FRAME_MARKER)
            except ValueError:
                self._buffer.clear()
                break
            if marker:
                del self._buffer[:marker]
            if len(self._buffer) < 4:
                break
            length = self._buffer[1] | (self._buffer[2] << 8)
            if length > CONNECT_MAX_PAYLOAD:
                del self._buffer[0]
                continue
            frame_length = length + 4
            if len(self._buffer) < frame_length:
                break
            payload = bytes(self._buffer[4:frame_length])
            expected_checksum = self._buffer[3]
            del self._buffer[:frame_length]
            if connect_xor(payload) == expected_checksum:
                messages.append(payload)
        return messages


def parse_connect_payload(payload: bytes | str) -> dict[str, Any] | None:
    """Parse and normalize one Connect-generation JSON response."""
    try:
        decoded = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError):
        return None
    if not isinstance(decoded, dict):
        return None
    message: dict[str, Any] = dict(decoded)
    message["protocol"] = "connect"
    cmd = message.get("cmd")
    if cmd in (
        CONNECT_QUERY_STATUS,
        CONNECT_RESPONSE_ALL_INFO,
        CONNECT_RESPONSE_STATUS,
    ) and isinstance(message.get("power"), int):
        message["battery_level"] = message["power"]
    return message


def encode_connect_query(command: int) -> list[bytes]:
    """Build a query command such as 200 (all info) or 214 (features)."""
    if not 0 <= command <= 0xFFFF:
        raise ValueError("command must be between 0 and 65535")
    return encode_connect_message({"cmd": command})


def encode_connect_work_mode(command: str | int, point: int | None = None) -> list[bytes]:
    """Set stop/work/home/trim/start-point mode (request command 101)."""
    if isinstance(command, str):
        try:
            mode = CONNECT_WORK_MODES[command.strip().lower()]
        except KeyError as err:
            raise ValueError(f"Unsupported Connect work mode: {command}") from err
    else:
        mode = command
    if mode not in {0, 1, 2, 4, 5}:
        raise ValueError("Connect work mode must be 0, 1, 2, 4, or 5")
    message: dict[str, Any] = {"cmd": CONNECT_SET_WORK_MODE, "mode": mode}
    if point is not None:
        if not 0 <= point <= 255:
            raise ValueError("point must be between 0 and 255")
        message["point"] = point
    return encode_connect_message(message)


def encode_connect_rain(enabled: bool, delay: int) -> list[bytes]:
    """Set rain mowing and the firmware's integer rain delay value."""
    if delay < 0:
        raise ValueError("delay must not be negative")
    return encode_connect_message(
        {"cmd": CONNECT_SET_RAIN, "rain_en": enabled, "rain_delay_set": delay}
    )


def encode_connect_ultrasonic(enabled: bool | int, level: int) -> list[bytes]:
    """Set ultrasonic obstacle sensing and sensitivity level."""
    if not 0 <= level <= 255:
        raise ValueError("level must be between 0 and 255")
    return encode_connect_message(
        {
            "cmd": CONNECT_SET_ULTRASONIC,
            "ultra_en": int(bool(enabled)),
            "ultra_lv": level,
        }
    )


def encode_connect_language(language: str | int) -> list[bytes]:
    """Set the mower language using the Connect app's 22-entry table."""
    if isinstance(language, int):
        code = language
    else:
        normalized = language.strip().lower()
        try:
            code = next(i for i, item in enumerate(CONNECT_LANGUAGES) if item.lower() == normalized)
        except StopIteration as err:
            raise ValueError(f"Unknown Connect language: {language}") from err
    if not 0 <= code < len(CONNECT_LANGUAGES):
        raise ValueError(f"Unknown Connect language code: {code}")
    return encode_connect_message({"cmd": CONNECT_SET_LANGUAGE, "language": code})


def encode_connect_time(value: datetime) -> list[bytes]:
    """Synchronize date, time, and weekday using the app's packed integers."""
    ymd = value.year * 10000 + value.month * 100 + value.day
    hms = value.hour * 10000 + value.minute * 100 + value.second
    return encode_connect_message(
        {"cmd": CONNECT_SET_TIME, "ymd": ymd, "hms": hms, "week": value.isoweekday() % 7}
    )


def encode_connect_pin(pin: str, *, verify_only: bool = False) -> list[bytes]:
    """Set or submit the mower's four-digit local PIN."""
    if len(pin) != 4 or not pin.isdecimal():
        raise ValueError("PIN must be exactly 4 decimal digits")
    # SetPasswdParams and SetInputPwdParams deliberately have the same JSON
    # fields; request context determines whether firmware verifies or stores it.
    command = CONNECT_VERIFY_PIN if verify_only else CONNECT_SET_PIN
    return encode_connect_message({"cmd": command, "passwd": int(pin)})


def encode_connect_device_name(name: str) -> list[bytes]:
    """Set the local mower name."""
    normalized = name.strip()
    if not normalized:
        raise ValueError("name must not be empty")
    return encode_connect_message({"cmd": CONNECT_SET_DEVICE_NAME, "rename": normalized})


def encode_connect_wifi(ssid: str, password: str) -> list[bytes]:
    """Provision Wi-Fi credentials over the local BLE transport."""
    if not ssid:
        raise ValueError("ssid must not be empty")
    return encode_connect_message({"cmd": CONNECT_SET_WIFI, "ssid": ssid, "passwd": password})


def encode_connect_led(
    *,
    enabled: bool,
    color: str,
    mode: int,
    start: int,
    end: int,
    night: bool,
) -> list[bytes]:
    """Configure the Connect-generation mower LED feature."""
    return encode_connect_message(
        {
            "cmd": CONNECT_SET_LED,
            "led_en": int(enabled),
            "led_color": color,
            "led_mode": mode,
            "led_start": start,
            "led_end": end,
            "led_night": int(night),
        }
    )


def encode_connect_schedule(schedule: Mapping[str, Any]) -> list[bytes]:
    """Encode an APK-compatible schedule object with request command 103."""
    return encode_connect_message({**schedule, "cmd": CONNECT_SET_SCHEDULE})


def encode_connect_schedule_pause(paused: bool) -> list[bytes]:
    """Pause or resume the configured schedule."""
    return encode_connect_message({"cmd": CONNECT_SET_SCHEDULE_PAUSE, "pause": paused})


def encode_connect_gps(enabled: bool | int) -> list[bytes]:
    """Enable or disable the Connect electronic/GPS feature."""
    return encode_connect_message({"cmd": CONNECT_SET_GPS, "gps_en": int(bool(enabled))})


def encode_connect_reset_map() -> list[bytes]:
    """Build the Connect work-map reset command."""
    return encode_connect_message({"cmd": CONNECT_RESET_MAP})


def encode_connect_reset_device() -> list[bytes]:
    """Build the Connect factory/device reset command."""
    return encode_connect_message({"cmd": CONNECT_RESET_DEVICE})


def encode_connect_multi_area(
    *,
    enabled: bool,
    automatic: bool,
    mode: int,
    zones: Iterable[int],
    meters: Iterable[int],
    proportions: Iterable[int],
) -> list[bytes]:
    """Set all four Connect-generation multi-area slots."""
    zone_values = tuple(zones)
    meter_values = tuple(meters)
    proportion_values = tuple(proportions)
    if not all(len(values) == 4 for values in (zone_values, meter_values, proportion_values)):
        raise ValueError("zones, meters, and proportions must each contain four values")
    if any(value < 0 for value in (*zone_values, *meter_values, *proportion_values)):
        raise ValueError("multi-area values must not be negative")
    message: dict[str, Any] = {
        "cmd": CONNECT_SET_MULTI_AREA,
        "mul_en": enabled,
        "mul_auto": automatic,
        "mul_mode": mode,
    }
    for index in range(4):
        suffix = index + 1
        message[f"mul_zon{suffix}"] = zone_values[index]
        message[f"mul_meter{suffix}"] = meter_values[index]
        message[f"mul_pro{suffix}"] = proportion_values[index]
    return encode_connect_message(message)


def decode_connect_packets(packets: Iterable[bytes]) -> list[dict[str, Any]]:
    """Convenience helper for decoding a recorded notification sequence."""
    decoder = ConnectFrameDecoder()
    messages: list[dict[str, Any]] = []
    for packet in packets:
        for payload in decoder.feed(packet):
            parsed = parse_connect_payload(payload)
            if parsed is not None:
                messages.append(parsed)
    return messages
