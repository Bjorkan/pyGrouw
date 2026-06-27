"""Compatibility checks for behavior used by the Home Assistant integration."""
from __future__ import annotations

from pygrouw.const import (
    DAYE_MODE_IDLE,
    DAYE_MODE_MOWING,
    DAYE_MODE_MOWING_ALTERNATE,
    DAYE_MODE_RETURNING,
    DAYE_MOWING_MODE_CODES,
    DAYE_PRIMARY_SERVICE_UUID,
    SUPPORTED_LOCAL_NAME_PREFIXES,
)
from pygrouw.discovery import (
    has_supported_service_uuid,
    is_supported_bluetooth_name,
    is_valid_pin,
)
from pygrouw.protocol import encode_daye_command


def test_supported_bluetooth_names_include_home_assistant_matchers() -> None:
    """The library recognizes the same mower local-name prefixes as HA."""
    assert SUPPORTED_LOCAL_NAME_PREFIXES == (
        "Robot Mower_DYM",
        "RobotMower_DYM",
        "Robot_Mower",
    )
    assert is_supported_bluetooth_name("Robot Mower_DYM")
    assert is_supported_bluetooth_name("RobotMower_DYM")
    assert is_supported_bluetooth_name("Robot_Mower")


def test_supported_service_uuid_includes_home_assistant_matcher() -> None:
    """The library recognizes the confirmed hardware GATT service UUID."""
    assert DAYE_PRIMARY_SERVICE_UUID == "49535343-fe7d-4ae5-8fa9-9fafd205e455"
    assert has_supported_service_uuid([DAYE_PRIMARY_SERVICE_UUID.upper()])


def test_pin_validation_matches_home_assistant_config_flow() -> None:
    """The Daye mower PIN shape remains the same as the HA config flow."""
    assert is_valid_pin("1234")
    assert not is_valid_pin("")
    assert not is_valid_pin("123")
    assert not is_valid_pin("12345")
    assert not is_valid_pin("12a4")


def test_lawn_mower_mode_constants_match_home_assistant_activity_mapping() -> None:
    """Mode bytes used by HA lawn mower activity mapping remain stable."""
    assert DAYE_MODE_MOWING == 0x00
    assert DAYE_MODE_MOWING_ALTERNATE == 0x01
    assert DAYE_MOWING_MODE_CODES == frozenset({0x00, 0x01})
    assert DAYE_MODE_RETURNING == 0x03
    assert DAYE_MODE_IDLE == 0x14


def test_start_mowing_command_payloads_cover_home_assistant_station_logic() -> None:
    """HA sends start from dock and resume when already away from station."""
    assert encode_daye_command("start").hex() == (
        "44594d01020000000000000000000000000000160601ff0a"
    )
    assert encode_daye_command("resume").hex() == (
        "44594d01000000000000000000000000000000160601ff0a"
    )
