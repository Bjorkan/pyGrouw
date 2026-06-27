# Java And Kotlin Findings

Last updated: 2026-06-26.

Findings from jadx-decompiled Java/Kotlin sources. These describe app plumbing
around Flutter, Gizwits, and FlutterBluePlus. They are not, by themselves,
wire-protocol proof for the Home Assistant BLE path.

## DayeGizPlugin

`DayeGizPlugin.java` registers:

```text
MethodChannel: daye_giz_plugin
EventChannel:  daye_giz_event_channel
```

It routes Flutter calls to the `GizWifiSDKProxy` Kotlin singleton.

Known Flutter channel method names found in `libapp.so` strings:

```text
bt_control_mower
bt_rain_delay_setting
changeMowerControl
getMowerSetting
mowerControl
didReceiveData
didReceiveAttrStatus
didSetSubscribe
deviceList
getDeviceStatus
write
```

The `write` method sends binary byte arrays to Gizwits devices.

## GizWifiSDKProxy

`GizWifiSDKProxy.kt` bridges the Gizwits SDK to Flutter.

Capabilities:

- user registration, login, logout, password reset/change
- bind, unbind, get bound devices, subscribe, get device status
- set custom device info
- write binary data through `GizWifiDevice.write(ConcurrentHashMap)` keyed by
  `"binary"`

Responses arrive via `didReceiveAttrStatus`, with raw binary data converted to
`List<Integer>` unsigned byte values.

`device2Json` serializes fields such as `mac`, `did`, `productKey`,
`ipAddress`, `isLAN`, `netStatus`, and `netType`.

## AppConfig

Gizwits cloud credentials found in the APK:

```text
appId:         01f37cba4e304eae8370ccd2feeaa53a
appSecret:     ad380615f8af4788927e98c221894581
productKey:    b50da224cd6745ababa0274c5607c4ad
productSecret: 989817f3ea0548d7b3c0ba9d21d7090e
```

These are APK facts only. The Home Assistant integration is local BLE and does
not use the Gizwits cloud.

## FlutterBluePlusPlugin

`FlutterBluePlusPlugin.java` is the standard Android plugin used by the app.

Relevant behavior:

- scan, connect, disconnect
- discover services
- read/write characteristic
- set notify
- request MTU
- read RSSI
- callbacks for connection state, discovered services, characteristic
  received/written, descriptor written, MTU changed
- `onCharacteristicReceived` sends a hex string in the `"value"` field
- uses a semaphore mutex to serialize BLE operations
- supports scan filters by service UUID, device address, device name,
  manufacturer data, and service data
