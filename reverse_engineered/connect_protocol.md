# Robotic Mower Connect BLE Protocol

Last updated: 2026-10-31.

This is the newer Grouw-local protocol statically recovered from Robotic Mower
Connect 1.4.5 (`com.cj.lawnmower`, APK SHA-256
`8b36e348c2c50b301b661c3677dcbffde765cfb9ee75ee2a81a075490c20a916`).
It is distinct from DYM and has not been validated on physical hardware.

## Transport

- Service: `0000fff0-0000-1000-8000-00805f9b34fb`
- Notify: `0000fff1-0000-1000-8000-00805f9b34fb`
- Write: `0000fff2-0000-1000-8000-00805f9b34fb`
- Marker: `0xa4`
- Header: marker, two-byte little-endian payload length, payload XOR
- Body: compact UTF-8 JSON
- Packet size: 20 bytes
- Recovered payload ceiling: 3000 bytes

## Queries

| Request | Response | Data |
| ---: | ---: | --- |
| 200 | 500 | all mower information |
| 201 | 501 | work/status information |
| 203 | 503 | schedule |
| 205 | 505 | rain settings/state |
| 207 | 507 | multi-area settings |
| 208 | 508 | device information |
| 212 | 512 | battery identity/history |
| 214 | 514 | supported feature flags |

## Setters and controls

The app's Kotlin call sites often visibly pass `0`, but a default-argument mask
replaces that value with the command listed below before JSON serialization.

| Request | Operation |
| ---: | --- |
| 101 | work mode/start point |
| 102 | date, time, weekday |
| 103 | weekly schedule |
| 104 | verify local PIN |
| 105 | rain settings |
| 106 | language |
| 107 | device name |
| 108 | multi-area settings |
| 109 | Wi-Fi credentials |
| 110 | change PIN |
| 111 | OTA/update initiation |
| 112 | device reset |
| 114 | ultrasonic sensing |
| 115 | LED settings |
| 116 | GPS/electronic feature |
| 121 | work-map reset |
| 127 | schedule pause |

Work modes are stop `0`, work `1`, home `2`, trim `4`, and start-point `5`.
Weekdays follow Java `Calendar.DAY_OF_WEEK - 1`: Sunday `0` through Saturday
`6`.

Schedule command `103` contains `auto`, `pause`, and `Mon` through `Sun`. Each
day contains `Trimming` and a `slice` list whose entries contain `start` and
`end`. The app divides received raw `mul_meter1` through `mul_meter4` values by
`1000` for display.

Battery response `512` exposes `bat_type`, `bat_id`, `bat_ctimes`, `bat_dtimes`,
`bat_change`, and `result`. Feature response `514` exposes integer fields
`schedule`, `rain`, `multizone`, `ultra`, `led`, `gps`, `info_stat`, `iot`,
`map`, `zone_ex`, `sche_ex`, and `add_func`; their raw integer values are
preserved because all value semantics have not been hardware-validated.

The parser recognizes generic acknowledgement `400` (including its originating
`command`), rename result `502`, PIN result `504`, map-reset result `523`, and
stop/work/home results `10100`/`10101`/`10102`. The Python client matches generic
acknowledgements to the originating request when the field is present, rejects
explicit negative results, and refreshes setter state with query `200`. Device
reset `112` is write-only in the client because the app waits 10 seconds and
then refreshes all information while the mower may reboot.

## Evidence and limitations

- framing: `ev_703813f4b998297763a2f9f9c5c5fe23fc1e6ac931c1ba94f65fc369eff53c52`
- reassembly: `ev_a200e9bcaf33699773a36342d2f4b0ba9d8019936b8bdb9b81c5f245b13072b5`
- response parser: `ev_39d4e29f9e2f9580a68bc6e445cd63ee6cd0baef7bc7a489d2d1b85ea22db919`
- work modes: `ev_b8061b307938c56c1c897523755781bd7429c973aef617716bc4ff0e15f95dd0`
- setter defaults: `ev_298ad02c2756b02c2b128503cd5cd5d1ecfbc6b95fb22b8fd4ac8b52c628ffdc`,
  `ev_b49794d104eefbd9400f91f5862f44b2f20d2b72e61862de77df1afd5ac651ea`,
  `ev_b66da44bbef77bbca16d1e0e188aa0fb1ec773df099cba55b4b3aae614eb4fba`,
  `ev_d89b3277cc2721600191231e6d2c823bd407e3539caeaa0c1b51bcd2afdb4c6f`
- response fields and BLE/MQTT distinctions:
  `ev_51f122a1235c5cc8be1324c63d5e5364d376d073417ad71bb9e35c388c158b39`,
  `ev_1f691204e9bd42c7ade487823d18d9822d9900874d4fb535974a13111e838d6f`
- reset commands and reset flow:
  `ev_6e84df6ae486186ac8125601ce86b3d95fa853c7e0596d2e9210e5625ca8cac8`,
  `ev_706313c5941a94710780ffbd9aded6ce02aee5764dd774b730c553bdc9eece2b`,
  `ev_425b19553f52e87ad85c749345331a0ab62cd233537d8216ea5ed205bdd2b698`

These are static shipped-artifact observations. REA did not execute the APK,
observe Bluetooth traffic, or contact a mower. Field units and firmware-specific
acceptance remain subject to hardware validation.
