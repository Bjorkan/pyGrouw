# Sources

Last updated: 2026-06-26.

Only the Daye APK and redacted hardware captures are authoritative for current
wire-protocol facts. Local manuals can corroborate product behavior and model
boundaries, but they do not define BLE packet semantics.

## Authoritative Sources

### Daye Power APK

```text
Package:      com.dayepower.dayeappleaf
Version:      2.0.1
Version code: 117
```

Play Store:

```text
https://play.google.com/store/apps/details?id=com.dayepower.dayeappleaf
```

Local APK/decompiler artifacts are under `APK/` and are not committed.

Relevant local findings:

- `manifest.json` confirms package, version, and version code.
- `decoded/jadx/resources/lib/arm64-v8a/libapp.so` contains Flutter/Dart
  strings for `romow_bluetooth`, `flutter_blue_plus`, and DYM Bluetooth setup.
- `blutter_out/asm/` was used to inspect Dart AOT symbols for `MainLogic`,
  `MowerStatusLogic`, `DeviceLogic`, `BlueKey`, FlutterBluePlus BLE flow,
  `ChangePinLogic`, `MowerSettingLogic`, `MultiAreaMowingLogic`, and
  `WorkingTimeSettingLogic`.

### Hardware Scan

An iPhone BLE scan near the mower on 2026-06-25 captured the local name and
GATT table. Durable findings are summarized in [gatt_table.md](gatt_table.md).

### HCI Snoop Captures

Android Bluetooth HCI snoop bugreports captured on 2026-06-25.

Captured user actions included:

- connect
- enter PIN `1234`
- start from dock
- stop
- start/resume after stop
- go to base station

Durable findings are summarized in [dym_protocol.md](dym_protocol.md).

## Corroborating Sources

Local Grouw manuals reviewed on 2026-06-26:

```text
APK/Manuals/libble-eu.pdf  Models 17935/17936/17937
APK/Manuals/b74925.pdf     Models 17941/17947
APK/Manuals/578ac6.pdf     Models 18739/18740 CLEVR
```

Durable findings are summarized in [manual_findings.md](manual_findings.md).

## Excluded Sources

Do not use these as protocol facts for this integration:

- the previous `com.cj.lawnmower` app
- old local reverse-engineering notes from unrelated app generations
- CLEVR / `robotic-mower connect` manuals as DYM packet evidence
- unredacted logs, raw captures, or screenshots with private data

## Do Not Commit

Never commit:

- official APK files
- extracted APK trees
- decompiled Java/smali/Dart/native output
- native library dumps
- local manuals or generated manual text
- raw HCI logs
- logs containing BLE addresses, serial numbers, PINs, credentials, or other
  private data
