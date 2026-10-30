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
| 214 | 514 | supported feature flags |

## Setters and controls

Setters use JSON request command `0`. Recovered fields cover work mode,
start-point, rain, ultrasonic sensing, language, PIN, date/time, rename, Wi-Fi
credentials, LED settings, schedule/pause, and four multi-area slots. Work mode
values are stop `0`, work `1`, home `2`, trim `4`, and start-point `5`.

The parser recognizes generic acknowledgement `400`, rename result `502`, PIN
result `504`, and stop/work/home results `10100`/`10101`/`10102`. The Python
client accepts the relevant result family, rejects explicit negative results,
and refreshes command state with query `200`.

## Evidence and limitations

- framing: `ev_703813f4b998297763a2f9f9c5c5fe23fc1e6ac931c1ba94f65fc369eff53c52`
- reassembly: `ev_a200e9bcaf33699773a36342d2f4b0ba9d8019936b8bdb9b81c5f245b13072b5`
- response parser: `ev_39d4e29f9e2f9580a68bc6e445cd63ee6cd0baef7bc7a489d2d1b85ea22db919`
- work modes: `ev_b8061b307938c56c1c897523755781bd7429c973aef617716bc4ff0e15f95dd0`

These are static shipped-artifact observations. REA did not execute the APK,
observe Bluetooth traffic, or contact a mower. Field units and firmware-specific
acceptance remain subject to hardware validation.
