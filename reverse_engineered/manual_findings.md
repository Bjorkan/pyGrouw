# Grouw Manual Findings

Last updated: 2026-06-26.

Reviewed from local PDFs under `APK/Manuals/`. The PDFs and extracted text are
local-only reference material and must not be committed.

Manuals can corroborate model boundaries and user-facing behavior. They do not
define BLE packet bytes.

## Reviewed Manuals

```text
APK/Manuals/libble-eu.pdf  Models 17935/17936/17937
APK/Manuals/b74925.pdf     Models 17941/17947
APK/Manuals/578ac6.pdf     Models 18739/18740 CLEVR
```

## Models 17935/17936/17937

- Bluetooth and app control are listed as supported.
- Factory PIN is `1-2-3-4`.
- Control panel supports daily work-time choices of 4, 6, 8, 10, or 12 hours.
- Manual recommends starting at 09:00.
- App multi-zone fields are named `Area2_Per`, `Area2_Dis`, `Area3_Per`, and
  `Area3_Dis`.
- Distance fields are described as metres along the boundary wire to the start
  point.
- Boundary cut is described as a factory-programmed weekly boundary-wire cut,
  depending on software version.
- Rain behavior is product behavior: return to charging station, charge, then
  wait after the sensor is dry before mowing again.
- Firmware can be updated by USB and, according to the Bluetooth guide,
  wirelessly over Bluetooth.
- The extracted text does not expose UUIDs, payloads, or a BLE device name.

## Models 17941/17947

- Bluetooth and app control are supported from both mower panel and app.
- App setup says to tap `Connect Bluetooth` and select `RobotMower_DYM`.
- The app requires the mower PIN after Bluetooth connection.
- Factory PIN is `1-2-3-4`.
- Panel menus align with APK BlueKey page findings:
  `Mow in the rain`, `Set work time`, `Boundary cut`, `Change PIN`, `Alert`,
  and `Time of Machine`.
- `Alert` shows the two most recent error codes.
- `Time of Machine` shows total operating time.
- Battery display is graphical; an empty-looking indicator means below 30%.
- `Mow in the rain` defaults to `No`.
- `Boundary cut` cuts along the boundary cable once per week.
- User-facing errors include `Mower trapped`, `Mower lifted`,
  `Boundary signal error`, `Battery temperature abnormal`, `Charge error`, and
  `Hall error`.

These labels are UI/product context, not protocol constants until captures
connect them to notification bytes.

## Models 18739/18740 CLEVR

- Different IoT generation.
- Uses app `robotic-mower connect`.
- Describes account registration, QR/serial onboarding, 2.4 GHz Wi-Fi, and
  Bluetooth 4.0.
- Manual Bluetooth pairing uses `Mower_XXXXXX`, not `RobotMower_DYM`.
- Factory PIN is `0000`.
- App commands can be delayed until mower returns to Wi-Fi coverage.
- Mower can be controlled over Wi-Fi away from home.
- App exposes schedules, edge trimming, map/start-point setup, rain delay,
  Wi-Fi settings, device parameters, firmware update, and logs.

Treat this as a separate generation. Do not mix its names or onboarding
assumptions into the current DYM BLE integration without separate captures.

## Integration Impact

- DYM-era manuals support a required 4-digit PIN and factory PIN `1-2-3-4`.
- The 17941/17947 manual supports the `RobotMower_DYM*` discovery alias.
- The 18739/18740 CLEVR manual does not justify `Mower_XXXXXX` discovery for
  this integration.
- Manuals do not reveal additional BLE UUIDs, DYM payloads, notification
  layouts, checksums, or encryption details.
- Treat rain, boundary cut, multi-area, working time, alert history, total
  runtime, and firmware update as product/app settings until hardware captures
  confirm exact wire behavior.
