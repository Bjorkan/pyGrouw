# Java And Kotlin Findings

Last updated: 2026-10-30.

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

REA/JADX revalidated the bundled plugin directly from base APK SHA-256
`dff783703aae15ef901ed19398807c61d4d0a91388e1deb92a06d96e781feac2`:

- Flutter write-with-response maps to Android `WRITE_TYPE_DEFAULT`; writes are
  rejected when another GATT operation is already active.
- notification setup calls `setCharacteristicNotification`, then writes the
  CCCD value for notifications or indications;
- service discovery, characteristic reads/writes, descriptor writes, and MTU
  requests are serialized by the plugin's operation mutex;
- `requestMtu` forwards the requested integer to Android; and
- normal writes are limited to `min(MTU - 3, 512)` bytes. Only the plugin's
  explicit long-write mode can use the separate 512-byte path.

Relevant REA Evidence IDs:

- plugin class inventory:
  `ev_2bf429d946abb28734c1f339e77e804d5c3d974ffeb076430675d4dcaa1d6b47`
- complete `onMethodCall` body:
  `ev_daaa86b5177cab2ab524b95936274ae6eed49507a8c7b3c97f69b8c9c515a773`
- `getMaxPayload` body:
  `ev_55ce174599cf2e9f2419ca8e7bb4b5c37cd6e211fccdfbffac770d3a3ef88741`

This proves behavior of the Android plugin bundled in the app. It does not, by
itself, prove which Flutter call path was used during a specific mower session.
