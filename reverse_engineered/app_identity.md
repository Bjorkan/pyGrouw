# App Identity And BLE Discovery

Last updated: 2026-06-26.

## Daye APK Identity

```text
Package:      com.dayepower.dayeappleaf
Version:      2.0.1
Version code: 117
Flutter app:  romow_bluetooth
BLE library:  flutter_blue_plus
```

BLE names found in the APK:

```text
Robot Mower_DYM
RobotMower_DYM
Robot_Mower-
```

The app contains UI/routes for Bluetooth connection, mower control, mower
status, mower settings, firmware update, working-time settings, multi-area
mowing, rain mowing, rain delay, ultrasound, back-to-station, and go-to-work.

## UUIDs Found In The App

```text
49535343-1E4D-4BD9-BA61-23C647249616
49535343-fe7d-4ae5-8fa9-9fafd205e455
00002902-0000-1000-8000-00805f9b34fb
```

`00002902-0000-1000-8000-00805f9b34fb` is the standard Client
Characteristic Configuration descriptor.

## FlutterBluePlus Signals

Strings found in the APK include:

```text
service_uuid
characteristic_uuid
writeAndNotify
writeAll
writeFinalChunk
allow_long_write
blueWriteAndNotification
BmWriteCharacteristicRequest
BmSetNotifyValueRequest
OnDiscoveredServices
OnCharacteristicReceived
OnCharacteristicWritten
```

## Home Assistant Discovery Impact

The integration should match:

```text
Service UUID: 49535343-fe7d-4ae5-8fa9-9fafd205e455
Local names:  Robot Mower_DYM*, RobotMower_DYM*, Robot_Mower*
```

The integration uses characteristic
`49535343-1E4D-4BD9-BA61-23C647249616` for write and notify.

## Manual Corroboration

The Grouw 17941/17947 manual says users should select `RobotMower_DYM` from the
Bluetooth device list in the app and enter the mower PIN. This supports the
current discovery aliases.

The Grouw 18739/18740 CLEVR manual describes a different IoT generation:
`robotic-mower connect`, 2.4 GHz Wi-Fi, Bluetooth 4.0, manual pairing as
`Mower_XXXXXX`, and factory PIN `0000`.

Do not add `Mower_XXXXXX` discovery to this DYM integration without separate
hardware captures for that generation.
