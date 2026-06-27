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
