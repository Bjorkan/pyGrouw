# Response Parsing

Last updated: 2026-06-26.

This file records how the Daye app and the Home Assistant integration interpret
response bytes. DYM and BlueKey byte positions are not automatically
interchangeable.

## APK Helpers

### `Helper::parseBlueResult`

`Helper::parseBlueResult` at `0x46b01c` converts a byte list into a one-based
string map:

```text
result["byte1"] = string(payload[0])
result["byte2"] = string(payload[1])
result["byte3"] = string(payload[2])
...
```

No payload byte is skipped. Callback code then reads named keys such as
`byte5` or `byte13`.

### `Helper::tenToHex`

`Helper::tenToHex` at `0x46b1e8` parses a decimal string to an integer, formats
that integer as radix-16 text, then parses that text with radix 32.

For single decimal digits the result matches the input value. For values above
15 it is not a normal byte conversion. Example: decimal `"20"` becomes hex
text `"14"`, then parses as radix-32 integer `36`.

The integration mirrors this as `daye_ten_to_hex()` only for debug parsing of
APK-derived BlueKey responses.

## BlueKey Query Responses

### `queryInfo` (`sub_cmd 0x00`)

Parsed by `MowerStatusLogic::changeWorkType` and
`DeviceLogic::initDeviceInfo`.

```text
byte5   battery percentage for image selection
byte9   device info string segment
byte10  model prefix selector: 2 -> "DY", 3/4 -> "DM", else ""
byte11  device info string segment
byte12  device info string segment
byte13  work type value, see mapping below
byte14  area code / firmware version prefix
byte15  firmware version suffix
```

`DeviceLogic::initDeviceInfo` sends `BlueKey::queryInfo` with
`notifyType: "0x80"` and parses battery/device/version fields.

`MowerStatusLogic::changeWorkType` sends the same query with `canBack: true`
and `showTip: false`, but without `notifyType`, and parses `byte13` for the
status display.

### `queryPin` (`sub_cmd 0x18`)

Parsed by `MainLogic::pinToDevice`:

```text
byte5   PIN digit 1
byte6   PIN digit 2
byte7   PIN digit 3
byte8   PIN digit 4
byte9   area code string, default "0" when absent
```

The app concatenates `byte5` through `byte8` into `MainState.robotPin`.
`MainLogic::openDevice` then compares the entered PIN against that stored value.

### Change PIN (`sub_cmd 0x0c`)

Parsed by `ChangePinLogic::changePin`:

```text
byte5 = "0" means PIN change success
```

On success the app updates `MainState.robotPin`, clears the PIN controllers,
and shows a success toast.

### Mower Settings (`sub_cmd 0x32`)

Parsed by `MowerSettingLogic::getMowerSetting`:

```text
byte5   mowInTheRain, "1" = true
byte6   boundaryCut, "1" = true
byte7   ultrasound, "1" = true
byte8   helixSet, "1" = true
byte9   rain-delay hour text
byte10  rain-delay minute text
byte12  led, "1" = true
```

The app default string for missing boolean setting bytes is `"2003"` and the
UI only treats exact string `"1"` as enabled. Rain is therefore a settings
field in the Daye app, not a confirmed status byte.

### Multi-Area (`sub_cmd 0x3a`)

Parsed by `MultiAreaMowingLogic::getInfo`:

```text
byte5        area2Per text
byte6-byte8  area2Dis text, variable-width decimal assembly
byte9        area3Per text
byte10-12    area3Dis text, variable-width decimal assembly
```

Distance unit and exact packing remain unconfirmed.

### Working Time (`sub_cmd 0x28`)

Parsed by `WorkingTimeSettingLogic::initData`:

```text
byte4        response/display mode
byte5-byte11 one value per weekday, Monday through Sunday
byte12-18    paired value per weekday, Monday through Sunday
```

Mode `0x85` uses `"."` as the work-duration delimiter; other modes use `":"`.
Because `byte4` is response context rather than a stable request sub-command,
the integration uses raw-service request context when decoding debug responses.

### Error Memory (`sub_cmd 0x3c`)

```text
byte5   error type letter code: B/N/L/T/R/X/C/S/P/A
byte6   unknown error data
byte7   error code hex prefix
byte8   error code hex separator
byte9   error code hex suffix
byte10  error data after colon
byte11  error data suffix
byte12  ASCII decoded alert letter
```

Letter codes map to translation keys `alert_b`, `alert_n`, `alert_l`,
`alert_t`, `alert_r`, `alert_x`, `alert_c`, `alert_s`, `alert_p`, and
`alert_a`.

## BlueKey Work Mode Mapping

From `MowerStatusLogic::changeWorkType` callback at `0x4dd66c`, `byte13`
maps to:

```text
0x00 = not handled / fallthrough
0x01 = "Mowing"
0x02 = "Turn Forward"
0x03 = "Along Boundary"
0x04 = "Robot Back"
0x05 = "Lift"
0x06 = "Collision"
0x07 = "tilt"
0x08 = "Finding Boundary"
0x09 = "tracing Back"
0x0a = "Boundary Back"
0x0b = "Boundary Cutting"
0x0c = "Partition Work"
0x0d = "No Boundary"
0x0e = "Charging"
0x0f = "Waiting"
0x10 = "SPIRAL MOWING"
0x14 = translated "Stopped"
0x19 = "Error"
0x29 = "--" and triggers changeConnectStatus(true)
```

Lift, tilt, and charging are work-mode values here, not separate confirmed
status flags.

## Battery Handling In The App

The app displays battery with image assets instead of a numeric sensor:

```text
byte5 <= 25  -> battery25.png
26..50       -> battery50.png
51..75       -> battery75.png
> 75         -> battery100.png
```

Home Assistant exposes numeric battery only because DYM status byte 4 has been
observed as a percentage-like value.

## DYM Status Parsing In Home Assistant

For HCI-observed DYM `0x80` status responses, the integration uses:

```text
byte 4   battery percentage candidate
byte 7   station/docked candidate
byte 12  raw mode candidate
```

Real-hardware observations on 2026-06-26:

```text
0x00 = mowing
0x01 = mowing/active, exact distinction unknown
0x03 = returning home
0x14 = stopped / standing still
```

Home Assistant maps both DYM `0x00` and `0x01` to mowing activity. The
station/docked byte overrides mode when deriving activity.

Do not directly apply the BlueKey `byte13` work-mode table to DYM byte 12.
BlueKey has no `0x00` mowing branch, while DYM `0x00` is confirmed as mowing
on the tested mower.
