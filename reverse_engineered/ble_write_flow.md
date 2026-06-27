# BLE Write And Notification Flow

Last updated: 2026-06-26.

Findings from `MainLogic::writeAndNotify` (`0x461eb4`),
`MainLogic::blueWriteAndNotification` (`0x461fa4`), and related Daye app
classes.

## Connection Sequence

When the Daye app sees `BluetoothDevice.connectionState == connected`,
`MainLogic` awaits `BluetoothDevice::requestMtu` before showing the success
toast and calling `discoverServices`.

The bundled FlutterBluePlus implementation requests MTU 512 with a 15-second
timeout.

## Write/Notify Sequence

1. `Helper::writeAndNotify` resolves `MainLogic` through GetIt and forwards
   the payload, callback, and optional flags.
2. `MainLogic::writeAndNotify` checks the connection-type sentinel.
3. `MainLogic::blueWriteAndNotification` cancels the existing `resultListen`
   subscription.
4. It subscribes to `onValueReceived` on the write characteristic.
5. It writes the command bytes with `BluetoothCharacteristic::write`.
6. On notification, it calls `Helper::parseBlueResult`.
7. The parsed one-based byte map is passed to the callback closure.

`Helper::writeAndNotify` signature:

```text
writeAndNotify(payload, callback, {
  canBack,
  errorTip,
  noLimitNotify,
  notifyType,
  showTip,
})
```

## `notifyType`

When `notifyType` is supplied, `blueWriteAndNotification` formats received byte
index 3, the fourth byte, as a padded hex string and compares it to
`notifyType` before invoking the callback.

This byte index is the same position as the DYM response command byte.

Observed `BlueKey::queryInfo` call sites:

```text
MowerStatusLogic::changeWorkType
  Helper.writeAndNotify(BlueKey.queryInfo, callback,
                        canBack: true, showTip: false)
  No notifyType filter. Callback reads byte13 for work-mode display.

DeviceLogic::initDeviceInfo
  Helper.writeAndNotify(BlueKey.queryInfo, callback,
                        notifyType: "0x80", errorTip: "Get info error")
  Callback reads byte5 battery and byte9-byte15 device/version fields.
```

This supports that app-side query/info handling can wait for response command
`0x80`, but does not prove that all DYM and BlueKey response fields share the
same semantics.

## State Classes

### MainState

```text
0x08  connectType
0x0c  area
0x10  robotPin
0x14  type
0x18  deviceName
0x1c  deviceAddress
0x20  loading
0x24  startTime
0x28  isOpenAuto
0x2c  haveBlueControll
```

### MowerStatusState

```text
0x08  disConnect
0x0c  workType
0x10  mowerControl
0x14  timer
```

### DeviceState

```text
0x08  connectType
0x0c  currentIndex
0x10  pageController
0x14  deviceInfo
0x18  batteryImage
0x1c  timer
```

### ChangePinState

```text
0x08  oldPin
0x0c  newPin
0x10  reNewPin
```

### MowerSettingState

```text
0x08  hour
0x0c  min
0x10  mowInTheRain
0x14  boundaryCut
0x18  ultrasound
0x1c  helixSet
0x20  led
0x24  timer
0x28  requestTimer
```

### MultiAreaMowingState

```text
0x08  area2Per
0x0c  area2Dis
0x10  area3Per
0x14  area3Dis
0x18  timer
0x1c  requestTimer
```

### WorkingTimeSettingState

```text
0x08  data
0x0c  type
0x10  day
0x14  startHour
0x18  startMinute
0x1c  workHour
0x20  workMinute
0x24  workMinuteList
0x28  startHourController
0x2c  startMinuteController
0x30  workHourController
0x34  workMinuteController
0x38  dayController
0x3c  timer
0x40  requestTimer
```
