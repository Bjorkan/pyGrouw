# BlueKey Commands

Last updated: 2026-06-26.

The Daye APK constructs BlueKey commands as 48-value `List<int>` payloads.
These are APK-derived findings from `common/config/blue_key.dart` and page
logic such as `MowerStatusLogic::manageDevice`.

Home Assistant currently uses BlueKey only for raw debug probes. Normal mower
entities and controls use HCI-confirmed DYM payloads.

## 48-Value Layout

```text
[0]     0x88            prefix byte 0
[1]     0xb2            prefix byte 1
[2]     0x9a            command marker
[3]     sub_cmd         sub-command byte
[4..18] data payload    15 command-specific values
[19]    44 / 0x2c       trailer value 0
[20]    12 / 0x0c       trailer value 1
[21]    2 / 0x02        trailer value 2
[22]    510 / 0x1fe     trailer value 3, stored as Dart int 510
[23]    20 / 0x14       trailer value 4
[24..47] 0              padding
```

`0x88` and `0xb2` are real payload values from the Dart constructors, not Dart
array metadata.

Python BLE writes require byte values. The Home Assistant debug encoder emits
each APK value as `value & 0xff`, so trailer value `510` becomes byte `0xfe`.
Keep this as a validation assumption until hardware captures confirm the
platform/native conversion.

## Sub-Commands

| Sub-command | Meaning |
| --- | --- |
| `0x00` | `queryInfo` |
| `0x04` | `setTime` |
| `0x0c` | `changePin` |
| `0x12` | `mowerSettingWrite` |
| `0x18` | `queryPin` |
| `0x28` | `workTime` |
| `0x32` | `mowerSettingQuery` |
| `0x3a` | `multiAreaQuery` |
| `0x3c` | `errorMemory` |

`0x0c`, `0x12`, `0x32`, and `0x3a` are built dynamically by page logic rather
than exposed only as static `BlueKey` fields.

## Static Payloads

```text
queryPin  sub_cmd 0x18, data[4..18]=0
setTime   sub_cmd 0x04, data[4]=0x28
queryInfo sub_cmd 0x00, data[4..11]=8 x 0x22
workTime  sub_cmd 0x28, data[4..18]=0
```

The `queryInfo` `0x22` values are unique to that sub-command. The app does not
compare them against response bytes in the decoded callback paths. Their exact
purpose is unknown.

## Control Commands

`MowerStatusLogic::manageDevice` builds 48-value control payloads at runtime.
The control value is stored in `[3]`:

```text
0 = start mowing
2 = stop
4 = go to work
6 = back to station
```

The dynamic payload still uses the same prefix, trailer, and padding shape.

## Page-Generated Commands

### Change PIN

`ChangePinLogic::changePin` validates the old PIN, repeated new PIN, and
minimum length before writing `sub_cmd 0x0c`.

```text
[4..7]   old/current PIN chunks via Helper.tenToHex
[8..11]  new PIN chunks via Helper.tenToHex
```

The response treats `byte5 == "0"` as success. The exact substring boundaries
in AOT output should be confirmed before implementing PIN-change writes.

### Mower Settings

`MowerSettingLogic::getMowerSetting` queries with `sub_cmd 0x32`.

`MowerSettingLogic::saveSetting` writes with `sub_cmd 0x12` and packs:

```text
mowInTheRain, boundaryCut, ultrasound, helixSet, hour, minute, led
```

The settings page gates some options by model/version strings such as
`DY002`, `DY052`, `DY012`, `DY112`, `GY002`, `GY052`, `GY012`, and `GY112`.
Exact outgoing bytes still need hardware validation.

### Multi-Area Mowing

`MultiAreaMowingLogic::getInfo` queries with `sub_cmd 0x3a`.

`MultiAreaMowingLogic::setInfo` writes area 2/3 percentage and distance fields:

```text
area2Per, area2Dis, area3Per, area3Dis
```

The page uses `Helper.tenToHex` while packing numeric text fields. Distance
unit and multi-byte packing remain unconfirmed.

### Working Time

`WorkingTimeSettingLogic::initData` writes static `BlueKey.workTime`
(`sub_cmd 0x28`) with `noLimitNotify = true`.

The page defaults each day to:

```text
start="09:00", work="3.0"
```

Save logic converts the seven day maps into fourteen values and branches on
the response/display mode (`byte4`, especially `0x85`) before writing updates.

## Relationship To DYM

HCI captures for the tested mower show DYM packets on the wire, not 48-byte
BlueKey writes. Possible explanations remain unconfirmed:

- DYM before auth and BlueKey after auth.
- Different firmware generations.
- Native-layer wrapping or translation.
- Device-type based protocol selection.

Do not use BlueKey payloads for normal entities or controls until captures
confirm the actual write path for the target firmware.

## Raw Debug Support

`grouw_ble_mower.send_raw_json` supports named BlueKey probes:

```json
{"bluekey": "query_info"}
{"bluekey": "set_time"}
{"bluekey": "query_pin"}
{"bluekey": "work_time"}
{"bluekey": "mower_settings"}
{"bluekey": "multi_area"}
{"bluekey": "error_memory"}
```

Generic probes can use `bluekey_sub_cmd` with optional `bluekey_data`.
Settings writes should stay in raw validation until captures confirm exact
bytes and mower behavior.
