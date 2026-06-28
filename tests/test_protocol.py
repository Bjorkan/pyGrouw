"""Tests for Grouw BLE framing."""
from __future__ import annotations

from pygrouw.protocol import (
    BLUEKEY_MOWER_SETTING_QUERY,
    BLUEKEY_MULTI_AREA_QUERY,
    BLUEKEY_QUERY_PIN,
    DAYE_RESPONSE_MOWER_SETTINGS,
    DAYE_RESPONSE_MULTI_AREA,
    DAYE_STATUS_REQUEST,
    MowerState,
    daye_ten_to_hex,
    encode_bluekey_command,
    encode_bluekey_payload,
    encode_daye_command,
    encode_daye_mower_settings,
    encode_daye_multi_area,
    encode_daye_session_start,
    encode_raw_payload,
    parse_daye_payload,
    redact_daye_message,
    state_from_message,
)


def test_encode_daye_command_returns_captured_status_poll() -> None:
    """The status poll matches the payload captured from the Daye app."""
    assert encode_daye_command("status") == DAYE_STATUS_REQUEST


def test_encode_daye_session_start_contains_current_time_payload() -> None:
    """The session start payload uses the captured DYM time-sync shape."""
    from datetime import datetime

    payload = encode_daye_session_start(datetime(2026, 6, 25, 18, 28))

    assert payload.hex() == "44594d02141a0619121c000000000000000000160601ff0a"


def test_encode_raw_payload_accepts_hex_and_command() -> None:
    """The debug service can send raw hex or a named captured command."""
    assert encode_raw_payload({"raw_hex": "44 59 4d"}) == b"DYM"
    assert encode_raw_payload({"command": "dock"}) == encode_daye_command("dock")
    assert encode_raw_payload({"command": "start"}) == encode_daye_command("start")
    assert encode_raw_payload({"command": "resume"}).hex().startswith("44594d0100")
    assert encode_raw_payload({"command": "bluekey_query_pin"}) == encode_bluekey_command(
        "query_pin"
    )
    assert encode_raw_payload({"bluekey": "query_pin"}) == encode_bluekey_command(
        "query_pin"
    )


def test_daye_ten_to_hex_matches_apk_helper_shape() -> None:
    """Helper.tenToHex is not a normal decimal-to-byte conversion."""
    assert daye_ten_to_hex("9") == 9
    assert daye_ten_to_hex("20") == 36


def test_encode_bluekey_command_matches_apk_layout() -> None:
    """Named BlueKey debug commands use the 48-byte APK layout."""
    payload = encode_bluekey_command("bluekey_query_info")

    assert len(payload) == 48
    assert payload[:12] == bytes.fromhex("88b29a002222222222222222")
    assert payload[19:24] == bytes.fromhex("2c0c02fe14")
    assert payload[24:] == b"\x00" * 24


def test_encode_bluekey_payload_accepts_generic_sub_command() -> None:
    """The debug encoder can build an APK-shaped BlueKey probe payload."""
    payload = encode_raw_payload({"bluekey_sub_cmd": "0x32", "bluekey_data": [1, 2]})

    assert len(payload) == 48
    assert payload[:6] == bytes.fromhex("88b29a320102")
    assert payload[19:24] == bytes.fromhex("2c0c02fe14")


def test_parse_daye_status_notification_maps_observed_fields() -> None:
    """Parse battery and mode bytes observed in the HCI snoop log."""
    message = parse_daye_payload(
        bytes.fromhex("44594d8064331b010004000100444100000000160601")
    )

    assert message == {
        "raw_hex": "44594d8064331b010004000100444100000000160601",
        "cmd": 0x80,
        "trailer": "160601",
        "battery_level": 0x64,
        "mode": 0x00,
        "station": True,
    }


def test_parse_daye_payload_ignores_non_dym_payload() -> None:
    """Non-Daye notifications are ignored."""
    assert parse_daye_payload(bytes.fromhex("01020304")) is None


def test_parse_daye_payload_does_not_decode_short_status_payload() -> None:
    """Only the captured 22-byte DYM status shape is decoded as state."""
    message = parse_daye_payload(bytes.fromhex("44594d806400160601"))

    assert message == {
        "raw_hex": "44594d806400160601",
        "cmd": 0x80,
        "trailer": "160601",
    }


def test_parse_daye_auth_response_extracts_numeric_pin_digits() -> None:
    """The auth/PIN response exposes the mower PIN as four digit bytes."""
    message = parse_daye_payload(
        bytes.fromhex("44594d8c0102030400000000000000000000160601")
    )

    assert message == {
        "raw_hex": "44594d8c0102030400000000000000000000160601",
        "cmd": 0x8C,
        "trailer": "160601",
        "mower_pin": "1234",
    }


def test_encode_daye_change_pin_matches_captured_payloads() -> None:
    """PIN change 1234 -> 4321 matches captured HCI payload."""
    from pygrouw.protocol import encode_daye_change_pin

    assert encode_daye_change_pin("1234", "4321").hex() == (
        "44594d06010203040403020100000000000000160601ff0a"
    )

    assert encode_daye_change_pin("4321", "1234").hex() == (
        "44594d06040302010102030400000000000000160601ff0a"
    )

    assert encode_daye_change_pin("1234", "1243").hex() == (
        "44594d06010203040102040300000000000000160601ff0a"
    )


def test_encode_daye_change_pin_validates_length() -> None:
    """PIN must be exactly 4 decimal digits."""
    from pygrouw.protocol import encode_daye_change_pin

    import pytest

    with pytest.raises(ValueError, match="PIN must be exactly 4 decimal digits"):
        encode_daye_change_pin("123", "1234")
    with pytest.raises(ValueError, match="PIN must be exactly 4 decimal digits"):
        encode_daye_change_pin("1234", "abc")


def test_parse_daye_pin_change_response() -> None:
    """A 0x86 response with all-zero payload indicates success."""
    message = parse_daye_payload(
        bytes.fromhex("44594d86000000000000000000000000000000160601")
    )

    assert message is not None
    assert message["cmd"] == 0x86
    assert message["pin_change_ack"] is True
    assert message["pin_change_success"] is True


def test_encode_daye_multi_area_matches_captured_payloads() -> None:
    """Multi-area writes match captured HCI payloads."""
    payload = encode_daye_multi_area(5, 12, 16, 74)
    assert payload.hex() == "44594d0d050001021000070400000000000000160601ff0a"

    payload = encode_daye_multi_area(0, 0, 0, 0)
    assert payload.hex() == "44594d0d000000000000000000000000000000160601ff0a"


def test_encode_daye_multi_area_validates_ranges() -> None:
    """Multi-area encoder validates percentage and distance ranges."""
    import pytest

    with pytest.raises(ValueError, match="area2_percentage"):
        encode_daye_multi_area(101, 0, 0, 0)
    with pytest.raises(ValueError, match="area2_distance"):
        encode_daye_multi_area(0, 1000, 0, 0)


def test_parse_daye_multi_area_response() -> None:
    """A 0x8d response is parsed into percentage and distance fields."""
    message = parse_daye_payload(
        bytes.fromhex("44594d8d000000000000000000000000000000160601")
    )

    assert message is not None
    assert message["cmd"] == DAYE_RESPONSE_MULTI_AREA
    assert message["multi_area"] == {
        "area2_percentage": 0,
        "area2_distance": 0,
        "area3_percentage": 0,
        "area3_distance": 0,
    }


def test_parse_daye_multi_area_response_non_zero_distance() -> None:
    """Non-zero distances are correctly decoded from decimal-chunk bytes."""
    message = parse_daye_payload(
        bytes.fromhex("44594d8d0501000110000704160601")
    )

    assert message is not None
    assert message["multi_area"] == {
        "area2_percentage": 5,
        "area2_distance": 101,
        "area3_percentage": 16,
        "area3_distance": 74,
    }


def test_encode_daye_mower_settings_matches_captured_payloads() -> None:
    """Mower settings writes match captured HCI payloads."""
    payload = encode_daye_mower_settings(
        mow_in_rain=True,
        boundary_cut=False,
        helix=True,
        rain_delay_hours=4,
        rain_delay_minutes=13,
    )
    assert payload.hex() == "44594d0901000001040d000000000000000000160601ff0a"

    payload = encode_daye_mower_settings(
        mow_in_rain=False,
        boundary_cut=False,
        helix=False,
        rain_delay_hours=0,
        rain_delay_minutes=0,
    )
    assert payload.hex() == "44594d09000000000000000000000000000000160601ff0a"

    payload = encode_daye_mower_settings(
        mow_in_rain=True,
        boundary_cut=True,
        helix=True,
        rain_delay_hours=4,
        rain_delay_minutes=13,
        unknown_setting=True,
    )
    assert payload[6] == 0x01
    assert payload.hex() == "44594d0901010101040d000000000000000000160601ff0a"


def test_encode_daye_mower_settings_validates_ranges() -> None:
    """Mower settings encoder validates rain delay ranges."""
    import pytest

    with pytest.raises(ValueError, match="rain_delay_hours"):
        encode_daye_mower_settings(
            mow_in_rain=False, boundary_cut=False, helix=False,
            rain_delay_hours=24, rain_delay_minutes=0,
        )
    with pytest.raises(ValueError, match="rain_delay_minutes"):
        encode_daye_mower_settings(
            mow_in_rain=False, boundary_cut=False, helix=False,
            rain_delay_hours=0, rain_delay_minutes=60,
        )


def test_parse_daye_mower_settings_response() -> None:
    """A 0x89 response is parsed into structured settings fields."""
    message = parse_daye_payload(
        bytes.fromhex("44594d89000100000000000000000000000000160601")
    )

    assert message is not None
    assert message["cmd"] == DAYE_RESPONSE_MOWER_SETTINGS
    assert message["mower_settings"] == {
        "mow_in_rain": False,
        "boundary_cut": True,
        "unknown_setting": False,
        "helix": False,
        "rain_delay_hour": 0,
        "rain_delay_minute": 0,
        "led": False,
    }


def test_redact_daye_message_hides_pin_and_auth_pin_bytes() -> None:
    """PIN values must not leak into diagnostics or normal debug logs."""
    redacted = redact_daye_message(
        {
            "raw_hex": "44594d8c0102030400000000000000000000160601",
            "cmd": 0x8C,
            "mower_pin": "1234",
        }
    )

    assert redacted == {
        "raw_hex": "44594d8c********00000000000000000000160601",
        "cmd": 0x8C,
        "mower_pin": "****",
    }


def test_parse_bluekey_query_pin_extracts_and_redacts_pin() -> None:
    """BlueKey queryPin responses expose the same PIN byte shape."""
    message = parse_daye_payload(encode_bluekey_payload(BLUEKEY_QUERY_PIN, [1, 2, 3, 4]))

    assert message is not None
    assert message["protocol"] == "bluekey"
    assert message["cmd"] == BLUEKEY_QUERY_PIN
    assert message["byte5"] == "1"
    assert message["mower_pin"] == "1234"
    assert redact_daye_message(message)["raw_hex"].startswith("88b29a18********")


def test_parse_bluekey_mower_settings_response() -> None:
    """Mower settings bytes are mapped from APK page logic."""
    message = parse_daye_payload(
        encode_bluekey_payload(
            BLUEKEY_MOWER_SETTING_QUERY,
            [1, 0, 1, 0, 2, 5, 0, 1],
        )
    )

    assert message is not None
    assert message["mower_settings"] == {
        "mow_in_rain": True,
        "boundary_cut": False,
        "ultrasound": True,
        "helix": False,
        "rain_delay_hour": 2,
        "rain_delay_minute": 5,
        "led": True,
    }


def test_parse_bluekey_multi_area_response() -> None:
    """Multi-area percentages and distance chunks are exposed for validation."""
    message = parse_daye_payload(
        encode_bluekey_payload(
            BLUEKEY_MULTI_AREA_QUERY,
            [30, 0, 12, 3, 40, 1, 2, 3],
        )
    )

    assert message is not None
    assert message["multi_area"] == {
        "area2_percentage": 30,
        "area2_distance": "123",
        "area3_percentage": 40,
        "area3_distance": "123",
    }


def test_parse_bluekey_work_time_uses_request_context() -> None:
    """Working-time parsing needs the request context because byte4 is a mode."""
    message = parse_daye_payload(
        encode_bluekey_payload(69, range(1, 16)),
        bluekey_context="bluekey_work_time",
    )

    assert message is not None
    assert message["bluekey_command"] == "work_time"
    assert message["work_time_mode"] == "0x85"
    assert message["work_time_delimiter"] == "."
    assert message["work_time"]["monday"] == {"primary": 1, "secondary": 8}


def test_state_from_message_maps_confirmed_dym_fields() -> None:
    """MowerState only updates fields confirmed from DYM status notifications."""
    previous = MowerState(address="AA:BB:CC:DD:EE:FF", battery_level=50)

    state = state_from_message(
        "AA:BB:CC:DD:EE:FF",
        {"cmd": 0x80, "battery_level": 75, "mode": 0x14, "station": False},
        previous,
    )

    assert state.battery_level == 75
    assert state.mode == 0x14
    assert state.station is False
    assert state.last_response_cmd == 0x80
    assert state.last_seen is not None
