# Native Telink Crypto

Last updated: 2026-06-26.

Findings from `libTelinkCrypto.so` and Java wrapper `com.telink.crypto.AES`.
These explain likely authentication/encryption support in the APK, but the
current Home Assistant integration does not implement native Telink crypto.

## `libTelinkCrypto.so`

The native library implements Telink AES-ATT helpers.

### AES Primitives

```text
0x0e98  _rijndaelSetKey
0x0f20  aes_sw_SwapRowCol
0x0f80  _rijndaelEncrypt
0x10a4  _rijndaelDecrypt
```

### AES-ATT Helpers

```text
0x1254  aes_att_swap                full 16-byte reversal
0x1278  aes_att_encryption_poly
0x1320  aes_att_decryption_poly
0x13d0  aes_att_encryption
0x14ac  aes_att_decryption
```

### Key Derivation

```text
0x158c  aes_att_er
0x1644  aes_att_get_sk
0x16e4  aes_att_get_ltk
0x1788  aes_att_enc_ltk
```

### Packet Processing

```text
0x182c  aes_att_command
0x186c  aes_att_network_info
0x189c  aes_att_encryption_packet
0x1a60  aes_att_decryption_packet
```

### State And JNI

```text
0x1c58  aes_att_set_crypto_poly
0x1c68  aes_att_get_crypto
0x1c78  GetNetworkName
0x1d14  GetMacAddress
0x1dbc  DeviceInNetowrk
0x1e2c  Java_com_telink_crypto_AES_encryptCmd
0x1f94  Java_com_telink_crypto_AES_decryptCmd
```

## AES-ATT Operations

Basic encryption flow:

```text
plaintext 16 bytes
-> aes_att_swap, full byte reversal
-> AES/ECB/NoPadding encrypt
-> aes_att_swap, full byte reversal
-> ciphertext 16 bytes
```

The polynomial variants add a MIC based on global `att_crypto_poly`
(`0x13040`). Observed default is zero, so polynomial MIC appears disabled by
default.

## LTK Derivation

`aes_att_get_ltk` at `0x16e4`:

```text
buffer = {param3[0..7], 0x0000000000000000}
temp   = param1 XOR param2 XOR buffer
LTK    = aes_att_decrypt(key, temp)
```

## Session Key Derivation

`aes_att_get_sk` at `0x1644`:

```text
key = param1 XOR param2
data = {param3[0..7], param4[0..7]}
SK = aes_att_encrypt(key, data)
```

## ER Helper

`aes_att_er` at `0x158c`:

```text
temp = param1 XOR param2
result = aes_att_encrypt(temp, {param3[0..7], zeros})
write result back to param3 first 8 bytes
```

## Java Wrapper

`com.telink.crypto.AES` wraps both Java AES and native Telink calls.

Two-argument methods use Java AES with byte reversal:

```java
SecretKeySpec keySpec = new SecretKeySpec(Utils.reverse(key), "AES");
Cipher cipher = Cipher.getInstance("AES/ECB/NoPadding");
return cipher.doFinal(Utils.reverse(data));
```

Three-argument methods call native JNI:

```java
encrypt(key1, key2, data) -> encryptCmd(data, key2, key1)
decrypt(key1, key2, data) -> decryptCmd(data, key2, key1)
```

`Security` is a static boolean flag. When false, encryption/decryption returns
the input data unchanged.

`Utils.reverse` performs a simple full byte-array reversal.

## Other Native Libraries

```text
libBLEasyConfig.so   BLE EasyConfig / Wi-Fi provisioning, not DYM control
libGizWifiDaemon.so  Gizwits SDK daemon support
libSDKLog.so         Gizwits logging support
```

## Telink UUID Table (`com.telink.crypto.UuidInformation`)

The Java wrapper `com.telink.crypto.UuidInformation` is an enum whose static
initializer hardcodes the Telink reference BLE UUIDs used by the Gizwits mesh
path. These are NOT the DYM `49535343-...` service; they are the vendor-neutral
"Telink SmartLight Service" set used by the Gizwits `BluetoothChannelEngine`.

```text
TELINK_SERVICE               00010203-0405-0607-0809-0a0b0c0d1910  "Telink SmartLight Service"
TELINK_CHARACTERISTIC_PAIR   00010203-0405-0607-0809-0a0b0c0d1914  "pair"
TELINK_CHARACTERISTIC_COMMAND 00010203-0405-0607-0809-0a0b0c0d1912 "command"
TELINK_CHARACTERISTIC_NOTIFY 00010203-0405-0607-0809-0a0b0c0d1911  "notify"
TELINK_CHARACTERISTIC_OTA    00010203-0405-0607-0809-0a0b0c0d1913  "ota"

SERVICE_DEVICE_INFORMATION   0000180a-0000-1000-8000-00805f9b34fb
CHARACTERISTIC_FIRMWARE      00002a26-0000-1000-8000-00805f9b34fb
CHARACTERISTIC_MANUFACTURER  00002a29-0000-1000-8000-00805f9b34fb
CHARACTERISTIC_MODEL         00002a24-0000-1000-8000-00805f9b34fb
CHARACTERISTIC_HARDWARE      00002a27-0000-1000-8000-00805f9b34fb
```

Evidence: `ev_54d056236cc6cfc5080e3a357aa2ae2dcbb6313859efb95e4652cf422e77f28a`.

## Manufacture Factory Config (`com.telink.crypto.Manufacture`)

`Manufacture` carries per-vendor factory secrets used as AES-ATT key-derivation
inputs. Its fields are `factoryName` (String), `factoryPassword` (String),
`factoryLtk` (byte[]), `vendorId` (int), `version` (String), `info` (String),
`otaSize` / `otaDelay` (int), and a `uuidMap` keyed by UUID role. A `Builder`
inner class exposes `setFactoryName/setFactoryPassword/setFactoryLtk` and the
per-role UUID setters, and `getFactoryLtk()/getFactoryPassword()/getFactoryName()`
return the configured values. `getDefaultManufacture()` returns the static
`DEFAULT_MANUFACTURE`; `getDefinitionManufacture()` returns the
runtime-set `definitionManufacture`.

Static incoming-reference tracing shows `Manufacture` and `AES` are referenced
only from the Gizwits SDK (`com.gizwits.gizwifisdk.api.SDKEventManager` and
`com.gizwits.gizwifisdk.api.GizMeshLocalControlCenter`), not from the Daye app's
own DYM/BlueKey Dart path. The factory LTK/password are therefore Gizwits-mesh
inputs, not DYM control inputs.

The `Manufacture.<clinit>` body (which builds `DEFAULT_MANUFACTURE`) could not be
disassembled by the JADX provider for this APK; its literal factory values remain
unrecovered from Java. The Gizwits SDK sets them at runtime.

Evidence: `ev_1d28d1a54eed15e8c609fd6eb8fa3dbb91ad7637b8ae07ce23c172c6fef0ac78`.
