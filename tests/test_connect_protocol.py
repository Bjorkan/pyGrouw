"""Tests for the Robotic Mower Connect BLE protocol."""

from __future__ import annotations

from datetime import datetime

import pytest

from pygrouw.connect_protocol import (
    ConnectFrameDecoder,
    connect_xor,
    decode_connect_packets,
    encode_connect_device_name,
    encode_connect_gps,
    encode_connect_language,
    encode_connect_led,
    encode_connect_multi_area,
    encode_connect_pin,
    encode_connect_query,
    encode_connect_rain,
    encode_connect_reset_device,
    encode_connect_reset_map,
    encode_connect_schedule,
    encode_connect_schedule_pause,
    encode_connect_time,
    encode_connect_ultrasonic,
    encode_connect_wifi,
    encode_connect_work_mode,
    frame_connect_payload,
)


def _payload(packets: list[bytes]) -> bytes:
    framed = b"".join(packets)
    length = framed[1] | (framed[2] << 8)
    assert framed[0] == 0xA4
    assert framed[3] == connect_xor(framed[4 : 4 + length])
    return framed[4 : 4 + length]


def test_connect_query_uses_apk_a4_length_xor_frame() -> None:
    packets = encode_connect_query(200)

    assert packets == [bytes.fromhex("a40b00647b22636d64223a3230307d")]


def test_connect_frame_splits_after_16_initial_payload_bytes() -> None:
    payload = b"x" * 37
    packets = frame_connect_payload(payload)

    assert [len(packet) for packet in packets] == [20, 20, 1]
    assert packets[0][4:] == b"x" * 16
    assert b"".join(packets)[4:] == payload


def test_connect_decoder_reassembles_fragmented_and_adjacent_frames() -> None:
    first = encode_connect_query(200)
    second = encode_connect_query(201)
    decoder = ConnectFrameDecoder()

    assert decoder.feed(first[0][:5]) == []
    decoded = decoder.feed(first[0][5:] + second[0])

    assert decoded == [b'{"cmd":200}', b'{"cmd":201}']


def test_connect_decoder_rejects_bad_checksum_and_recovers() -> None:
    bad = bytearray(encode_connect_query(200)[0])
    bad[3] ^= 0xFF
    good = encode_connect_query(201)[0]

    assert ConnectFrameDecoder().feed(bad + good) == [b'{"cmd":201}']


def test_connect_work_modes_match_app_values() -> None:
    assert _payload(encode_connect_work_mode("stop")) == b'{"cmd":101,"mode":0}'
    assert _payload(encode_connect_work_mode("start")) == b'{"cmd":101,"mode":1}'
    assert _payload(encode_connect_work_mode("dock")) == b'{"cmd":101,"mode":2}'
    assert _payload(encode_connect_work_mode("trim")) == b'{"cmd":101,"mode":4}'
    assert _payload(encode_connect_work_mode("start_point", 3)) == (
        b'{"cmd":101,"mode":5,"point":3}'
    )
    assert _payload(encode_connect_work_mode("pause")) == b'{"cmd":101,"mode":0}'
    assert _payload(encode_connect_work_mode("resume")) == b'{"cmd":101,"mode":1}'


def test_connect_settings_use_apk_json_field_names() -> None:
    assert _payload(encode_connect_pin("0123")) == b'{"cmd":110,"passwd":123}'
    assert _payload(encode_connect_pin("0123", verify_only=True)) == (b'{"cmd":104,"passwd":123}')
    assert _payload(encode_connect_device_name("Garden")) == b'{"cmd":107,"rename":"Garden"}'
    assert _payload(encode_connect_wifi("My WiFi", "secret")) == (
        b'{"cmd":109,"ssid":"My WiFi","passwd":"secret"}'
    )
    assert _payload(encode_connect_schedule_pause(True)) == b'{"cmd":127,"pause":true}'
    assert _payload(encode_connect_language("English")) == b'{"cmd":106,"language":4}'
    assert _payload(encode_connect_gps(True)) == b'{"cmd":116,"gps_en":1}'
    assert _payload(encode_connect_reset_map()) == b'{"cmd":121}'
    assert _payload(encode_connect_reset_device()) == b'{"cmd":112}'
    assert _payload(encode_connect_rain(True, 30)) == (
        b'{"cmd":105,"rain_en":true,"rain_delay_set":30}'
    )
    assert _payload(encode_connect_ultrasonic(True, 2)) == (
        b'{"cmd":114,"ultra_en":1,"ultra_lv":2}'
    )
    assert b'"cmd":115' in _payload(
        encode_connect_led(
            enabled=True,
            color="#ffffff",
            mode=1,
            start=1800,
            end=2300,
            night=True,
        )
    )


def test_connect_time_uses_packed_apk_values() -> None:
    assert _payload(encode_connect_time(datetime(2026, 10, 31, 14, 5, 9))) == (
        b'{"cmd":102,"ymd":20261031,"hms":140509,"week":6}'
    )
    assert b'"week":0' in _payload(encode_connect_time(datetime(2026, 11, 1, 12, 0)))


def test_connect_schedule_cannot_override_setter_command() -> None:
    assert _payload(
        encode_connect_schedule({"cmd": 999, "auto": True, "Mon": {"Trimming": False, "slice": []}})
    ) == (b'{"cmd":103,"auto":true,"Mon":{"Trimming":false,"slice":[]}}')


def test_connect_multi_area_encodes_four_slots() -> None:
    payload = _payload(
        encode_connect_multi_area(
            enabled=True,
            automatic=False,
            mode=2,
            zones=(1, 2, 3, 4),
            meters=(1000, 2000, 3000, 4000),
            proportions=(10, 20, 30, 40),
        )
    )
    assert b'"mul_zon4":4' in payload
    assert b'"mul_meter3":3000' in payload
    assert b'"mul_pro2":20' in payload
    assert b'"cmd":108' in payload


def test_decode_connect_packets_normalizes_status() -> None:
    packets = frame_connect_payload(
        b'{"cmd":500,"power":87,"mode":2,"station":false,"model":"G1","sn":"123"}'
    )

    assert decode_connect_packets(packets) == [
        {
            "cmd": 500,
            "power": 87,
            "mode": 2,
            "station": False,
            "model": "G1",
            "sn": "123",
            "protocol": "connect",
            "battery_level": 87,
        }
    ]


def test_direct_201_status_is_normalized_for_older_firmware_shape() -> None:
    packets = frame_connect_payload(b'{"cmd":201,"power":42,"mode":1}')

    assert decode_connect_packets(packets)[0]["battery_level"] == 42


def test_connect_validation_rejects_invalid_values() -> None:
    with pytest.raises(ValueError, match="PIN"):
        encode_connect_pin("12")
    with pytest.raises(ValueError, match="Unsupported Connect work mode"):
        encode_connect_work_mode("fly")
    with pytest.raises(ValueError, match="four values"):
        encode_connect_multi_area(
            enabled=True,
            automatic=False,
            mode=0,
            zones=(1,),
            meters=(1,),
            proportions=(1,),
        )
