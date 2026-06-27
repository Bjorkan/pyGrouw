# Reverse Engineered Protocol Notes

Last updated: 2026-06-26.

This directory is the durable protocol memory for the integration. Keep raw
APKs, decompiler output, manuals, HCI logs, and private captures out of git;
commit only summarized findings here.

## Start Here

Read in this order when orienting yourself:

1. [sources.md](sources.md) - what evidence is authoritative.
2. [app_identity.md](app_identity.md) - app package, BLE names, UUIDs.
3. [gatt_table.md](gatt_table.md) - hardware-scanned services and handles.
4. [dym_protocol.md](dym_protocol.md) - current on-wire protocol used by HA.
5. [response_parsing.md](response_parsing.md) - decoded notification fields.
6. [bluekey_commands.md](bluekey_commands.md) - APK-derived 48-value command
   format used only for debug probes so far.

## File Map

| File | Purpose |
| --- | --- |
| [sources.md](sources.md) | Evidence sources and local-only artifact rules |
| [app_identity.md](app_identity.md) | Daye app identity, BLE names, UUIDs, discovery impact |
| [gatt_table.md](gatt_table.md) | GATT table and HCI-confirmed characteristic details |
| [dym_protocol.md](dym_protocol.md) | HCI-confirmed DYM packet shapes, payloads, status fields |
| [response_parsing.md](response_parsing.md) | APK and DYM response parsing notes |
| [ble_write_flow.md](ble_write_flow.md) | Daye app write/notify flow and state classes |
| [bluekey_commands.md](bluekey_commands.md) | BlueKey command layout, sub-commands, debug probes |
| [dart_blutter_analysis.md](dart_blutter_analysis.md) | Dart AOT/blutter symbol findings |
| [native_crypto.md](native_crypto.md) | Telink native AES-ATT findings |
| [java_kotlin_findings.md](java_kotlin_findings.md) | Java/Kotlin plugin, Gizwits, FlutterBluePlus findings |
| [manual_findings.md](manual_findings.md) | Local Grouw manual findings and model boundaries |

## Current Protocol Picture

Home Assistant currently uses the HCI-confirmed DYM protocol:

```text
Outbound DYM write: 24 bytes, ASCII prefix "DYM"
Inbound status:     22 bytes, response command 0x80
Inbound auth/PIN:   response command 0x8c
```

The normal integration path uses DYM status/start/resume/pause/dock payloads
without the DYM session/auth prelude. Hardware validation showed the prelude
can trigger unwanted beeps, while the unauthenticated DYM status and command
payloads work on the tested mower.

The Daye APK also contains a BlueKey system that constructs 48-value payloads
with prefix `[0x88, 0xb2, 0x9a]`. Those findings are useful for research and
raw debug probes, but normal Home Assistant entities and controls do not use
BlueKey writes until captures prove the exact on-wire behavior for this mower
generation.

## Confirmed Highlights

- App package: `com.dayepower.dayeappleaf`.
- APK version reviewed: `2.0.1`, version code `117`.
- Confirmed BLE names: `Robot Mower_DYM`, `RobotMower_DYM`,
  `Robot_Mower-`.
- Confirmed service UUID: `49535343-fe7d-4ae5-8fa9-9fafd205e455`.
- Confirmed control characteristic:
  `49535343-1e4d-4bd9-ba61-23c647249616`.
- The app requests MTU 512 before service discovery.
- DYM response commands observed in Home Assistant:
  - `0x80` / decimal `128`: status/query response
  - `0x8c` / decimal `140`: auth/PIN response
- DYM mode observations:
  - `0x00`: mowing
  - `0x01`: mowing/active, exact distinction unknown
  - `0x03`: returning home
  - `0x14`: stopped / standing still
- The dock/station byte must override mode when deriving Home Assistant
  activity because stale-looking active modes can appear while docked.
- BlueKey `queryInfo` work-mode byte13 maps `0x01` to `"Mowing"` and has no
  `0x00` branch. Do not directly replace the DYM byte12 mapping with that
  table.

## Known Unknowns

- Exact meaning of every byte in the DYM `0x80` status response.
- Exact distinction between DYM mode `0x00` and `0x01`.
- Whether every DYM `0x80` field maps to the same fields as BlueKey
  `queryInfo`.
- Which firmware generations use DYM, BlueKey, or both.
- Exact packing for BlueKey settings writes, schedule writes, multi-area
  distance writes, and PIN change writes.
- Multi-area distance units on the wire.
- Exact key derivation inputs passed from Dart/Java to native Telink crypto.

## Validation Workflow

When validating real hardware:

1. Capture the user action sequence and the notification bytes.
2. Redact BLE addresses, serial numbers, PINs, credentials, and personal data.
3. Update the specific topic file first.
4. Update [README.md](../README.md), [DEVELOPMENT.md](../DEVELOPMENT.md), and
   [TESTING.md](../TESTING.md) when behavior, tests, or user-facing status
   changes.
5. Add or update tests when parser, entity, service, config flow, or BLE
   behavior changes.
