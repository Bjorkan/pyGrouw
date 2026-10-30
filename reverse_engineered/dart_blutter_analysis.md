# Dart AOT / Blutter Analysis

Last updated: 2026-06-26.

Findings from `libapp.so` after blutter analysis. Source paths point to the
Daye app's `romow_bluetooth` Flutter package.

## Library Units

### `@14069316` - Standard Dart Runtime

This unit is standard Dart runtime code (`dart:io`, `dart:async`,
`dart:collection`), not custom protocol code.

Functions such as `_sendData`, `_makeDatagram`, `_checkForErrorResponse`,
`_checkSum`, `_isBufferEncrypted`, `_onData`, and `_raw` appear here as Dart
runtime internals. Do not use them as evidence for mower BLE framing.

### `@8050071` - Binary Serialization

Typed load/store helpers:

```text
_storeUint8    _storeUint16   _storeUint32   _storeUint64
_storeInt8     _storeInt16    _storeInt32    _storeInt64
_loadUint8     _loadUint16    _loadUint32    _loadUint64
_loadInt8      _loadInt16     _loadInt32     _loadInt64
```

### Other Runtime-Like Units

```text
@3220832   checksum helper unit, includes _checkSum
@10003594  buffer creation helper unit, includes _createBuffer
```

## MainLogic

`pages/main/logic.dart`, class size `0x20`.

```text
0x461eb4  writeAndNotify
0x461fa4  blueWriteAndNotification
0x46ac3c  onDone closure
0x46aca4  onError closure
0x46ad84  onData closure
0x46b580  changePIN
0x46f4b4  resetPinInput
0x46f720  openDevice
0x47086c  setDevice
0x4709c4  connectionState callback
```

Connection flow: on BLE connected, the app awaits FlutterBluePlus
`requestMtu` before service discovery. The bundled FlutterBluePlus path
requests MTU 512 with a 15-second timeout.

## MowerStatusLogic

`pages/mower_status/logic.dart`, class size `0x24`.

```text
0x46db00  changeMoverControl
0x46db6c  stateDisConnect
0x470510  navigate back on disconnect dialog
0x470584  call disConnect on confirm
0x4705e4  disConnect
0x480bc0  changeConnectStatus
0x4dd444  addListen
0x4dd534  timer callback -> changeWorkType
0x4dd594  changeWorkType
0x4dd66c  response callback, byte13 -> work type
0x51b6a0  manageDevice
0x51c39c  errorMemory
0x51c4f4  error data callback
```

`changeWorkType` sends `BlueKey::queryInfo` and reads `byte13` for the work
mode display. `manageDevice` builds runtime BlueKey control commands for
start/stop/back/go-to-work.

## DeviceLogic

`pages/device/logic.dart`.

```text
0x47ff9c  onReady
0x47fff0  initDeviceInfo
0x480164  response callback
```

`initDeviceInfo` sends `BlueKey::queryInfo` once at init with
`notifyType: "0x80"`. Its callback parses `byte5` battery, `byte9-byte12`
device/version text, and `byte14-byte15` model/version values.

## Settings And PIN Logic

### ChangePinLogic

```text
0x461584  changePin
0x46b25c  response callback
0x665ef0  getChangePIN
```

The page packs old and new PIN chunks through `Helper.tenToHex`. Exact
substring boundaries should be confirmed before implementing writes.

### MowerSettingLogic

```text
0x48217c  saveSetting
0x6640fc  getMowerSetting
0x664378  response callback
```

Decoded state fields: `hour`, `min`, `mowInTheRain`, `boundaryCut`,
`ultrasound`, `helixSet`, `led`, `timer`, and `requestTimer`.

### MultiAreaMowingLogic

```text
0x48fff4  setInfo
0x664e44  getInfo
0x6650c4  response callback
```

Distance values are assembled from multiple bytes with leading-zero handling.
Units and exact outgoing packing remain unconfirmed.

### WorkingTimeSettingLogic

```text
0x498350  getSetList
0x678288  initData
0x6784bc  response callback
0x6788f8  getResult
```

Default daily values are `start="09:00"` and `work="3.0"`. Response mode
`0x85` uses `"."` for work-duration display; other modes use `":"`.

### LanguageSettingLogic

```text
0x481eb0  changeLanguage   -> write sub_cmd 0x06, code in byte 4
0x4830fc  changeSelectIndex
0x666a40  onReady
0x666a7c  getLanguage      -> write sub_cmd 0x26, zero data
0x666c9c  response closure -> tenToHex(byte5), match code table
```

`changeLanguage` builds a 19-entry code table (`0, 2, 4, ..., 36`) at runtime,
loads `LanguageSettingState.selectIndex`, and writes the selected code into
payload byte 4. `getLanguage` sends a zero-data `0x26` query and its response
closure maps `byte5` through `Helper.tenToHex` before matching the table.

`LanguageSettingState` (`state.dart`) stores the 19 ordered language strings
(English through Italiano) and a `selectIndex` field.

## Helper

`common/util/helper.dart`.

```text
0x42f7f0  cloudCallback
0x461c44  writeAndNotify
0x46b01c  parseBlueResult
0x46b1e8  tenToHex
0x47830c  diyPicker
```

When `notifyType` is supplied, `blueWriteAndNotification` formats received
byte index 3 as padded hex and compares it to `notifyType` before invoking the
normal parsed-map callback.

## BlueKey

`common/config/blue_key.dart`.

```text
Static fields:
  0xfa4  queryPin
  0xfa8  setTime
  0xfac  queryInfo
  0xfb0  workTime

Static methods:
  0x4719c0  setTime()    -> 48 values, sub-cmd 0x04
  0x47e78c  queryPin()   -> 48 values, sub-cmd 0x18
  0x4808e0  queryInfo()  -> 48 values, sub-cmd 0x00, data 8 x 0x22
  0x678ce4  workTime()   -> 48 values, sub-cmd 0x28
```

Commands are constructed as plain Dart `List<int>` values and sent through
`writeAndNotify` -> `blueWriteAndNotification` ->
`BluetoothCharacteristic::write`. No Dart-side encryption, DYM framing, or
checksum logic is visible in this path.

## BLE Write Call-Site Inventory

A bounded search of every `Helper::writeAndNotify` call and every direct
`BluetoothCharacteristic::write` in the recovered `romow_bluetooth` tree found
only the constructors already documented here. There is no additional
diagnostic, statistics, factory-reset, or standalone firmware-transfer write
in the Dart layer.

Direct `BluetoothCharacteristic::write` sites:

```text
pages/main/logic.dart  0x4621d8  blueWriteAndNotification (low-level writer)
pages/main/logic.dart  0x471538  setTime (BlueKey.setTime with replaceRange)
```

`Helper::writeAndNotify` sites, grouped by page:

```text
pages/main/logic.dart           0x47e498  pinToDevice (queryPin 0x18)
pages/mower_status/logic.dart   0x4dd64c  changeWorkType (queryInfo 0x00)
pages/mower_status/logic.dart   0x51ba38  manageDevice control (start 0x00)
pages/mower_status/logic.dart   0x51bad0  manageDevice control (stop 0x02)
pages/mower_status/logic.dart   0x51bb80  manageDevice control (go-to-work 0x04)
pages/mower_status/logic.dart   0x51bc30  manageDevice control (back 0x06)
pages/mower_status/logic.dart   0x51c4cc  errorMemory (0x3c)
pages/device/logic.dart         0x48013c  initDeviceInfo (queryInfo 0x00)
pages/change_pin/logic.dart     0x461bc8  changePin (0x0c)
pages/change_pin/logic.dart     0x665ff0  getChangePIN
pages/mower_setting/logic.dart  0x482a0c  saveSetting (0x12)
pages/mower_setting/logic.dart  0x664224  getMowerSetting (0x32)
pages/multi_area_mowing/logic.dart 0x490c9c  setInfo
pages/multi_area_mowing/logic.dart 0x664f6c  getInfo (0x3a)
pages/working_time_setting/logic.dart 0x498130  saveSetting
pages/working_time_setting/logic.dart 0x4982bc  saveSetting
pages/working_time_setting/logic.dart 0x67835c  initData (workTime 0x28)
pages/language_setting/logic.dart 0x482104  changeLanguage (0x06)
pages/language_setting/logic.dart 0x666c88  getLanguage (0x26)
```

## Package Paths Found

Representative package paths from `libapp.so` strings:

```text
common/config/blue_key.dart
common/services/gizwits_service.dart
common/util/dialog/dialog_util.dart
common/util/pop_scope_util.dart
pages/add_robot_model/{binding,logic,state,view}.dart
pages/add_robot_model/widget/robot_type_{1,2,3,4}.dart
pages/add_robot_finish/state.dart
pages/change_pin/logic.dart
pages/device/state.dart
pages/forgot_password/view.dart
pages/language_setting/state.dart
pages/main/view.dart
pages/mower_firmware_update/{binding,logic,state,view}.dart
pages/mower_setting/logic.dart
pages/mower_status/logic.dart
pages/multi_area_mowing/widget/input_card.dart
pages/privacy_policy/view.dart
pages/working_time_setting/logic.dart
```
