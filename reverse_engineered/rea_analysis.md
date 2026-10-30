# REA Analysis Ledger

Last updated: 2026-10-30.

This file records compact, non-sensitive findings from REA static inspection.
The APK, split APKs, extracted native libraries, and generated decompiler output
remain local-only and must never be committed.

## Artifact Identity

REA inventoried the supplied XAPK as a complete ZIP central-directory view:

```text
XAPK SHA-256: 69ea538b13097a32cbf2a23d08271f26de474c52bba7a48f009d5a89f953b667
Entries:       7 files (base APK, two ABI splits, two language splits,
               one density split, and manifest.json)
Contradictions: none observed in the inventoried entries
```

Relevant extracted identities:

```text
Base APK SHA-256:        dff783703aae15ef901ed19398807c61d4d0a91388e1deb92a06d96e781feac2
arm64 split SHA-256:     6c7c22877d0e4c2c6a4d07197663758138b9da57e6b068808a743561cde1b7cd
arm64 libapp.so SHA-256: a15277fc599b63f91b37a6fecdebf758eb6292fe93c377289006e3c937a9211f
```

Evidence:

- XAPK inventory summary:
  `ev_c9ef152214f9deb26d193af5d165fcae8a657aa145e8a5de7e416aae5060c400`
- XAPK extraction record:
  `ev_1cbd3f2a5811f8f64afb1b1eff94dca936fd831454c46f4ddeac9dcd606a9b38`

Archive inventory establishes artifact membership and byte identity. It does
not establish application runtime behavior.

## Dart AOT Observation

REA inspected `libapp.so` through the arm64 split APK. It observed a Dart
FullAOT kind-3 snapshot with hash `f71c76320d35b65f1164dbaa6d95fe09`.
The four VM/isolate data and instruction sections were located, and the
`libapp.so` section coverage was complete.

The projected string pool was partial because collection bounds were reached:

```text
Package URIs:      at least 769 (500 returned)
Dart URIs:         at least 204 (204 returned)
Class-like tokens: at least 4000 (2000 returned)
Printable runs:    21341
```

Evidence:

- Dart AOT summary:
  `ev_6a459129f2b1dfcbe87d581f955d60f987d79086e9f4261d07598df9ca49cad3`

The string-pool projection is byte-pattern evidence, not recovered typed Dart
classes or functions. Counts marked “at least” are lower bounds.

## APK Signing Records

REA observed v1, v2, and v3 signing records in the base APK. All three records
declare the same certificate SHA-256 fingerprint:

```text
b372369b15c125bfb7e3293f21afaa72326879d153f0f0b38d39645bf4afaaae
```

The strongest observed scheme is v3, no rotation lineage was declared, and a
source stamp was present. The records were structurally self-consistent.

Evidence:

- APK-signature summary:
  `ev_b904415a2ed45ee8c456a08fb412080097a74da56b6f714fcfd561f5566e9d58`

REA did not cryptographically verify signatures, certificate trust, revocation,
or authenticity. These are declared static identities, not a trust verdict.

## Android BLE Plugin

JADX coverage was complete for the 4,421 classes in the base APK. REA confirmed
that the bundled FlutterBluePlus Android plugin serializes GATT operations,
configures notification CCCDs, supports explicit MTU requests, and maps
write-with-response to Android `WRITE_TYPE_DEFAULT`. Its normal write payload
limit is `min(MTU - 3, 512)`.

Evidence:

- Android package summary:
  `ev_c66dba46f8f5ec47f0b4d96a6572d469b4737995292b0ed780c37d6b8b9c8772`
- FlutterBluePlus class:
  `ev_2bf429d946abb28734c1f339e77e804d5c3d974ffeb076430675d4dcaa1d6b47`
- complete `onMethodCall` body:
  `ev_daaa86b5177cab2ab524b95936274ae6eed49507a8c7b3c97f69b8c9c515a773`
- `getMaxPayload` body:
  `ev_55ce174599cf2e9f2419ca8e7bb4b5c37cd6e211fccdfbffac770d3a3ef88741`

This is static evidence for the plugin bundled in the official app, not a
runtime trace of a particular mower interaction.

## Library Changes Informed By The Review

The review was combined with the existing HCI-confirmed DYM packet shapes. The
library now:

- rejects malformed known DYM notifications instead of decoding short frames;
- validates bounded percentages, decimal chunks, booleans, times, and durations;
- treats DYM settings byte 11 as reserved instead of importing the BlueKey LED
  interpretation into DYM;
- redacts old and new PIN digits from outbound GATT success logs;
- requires both distinct work-time responses (`0x84` and `0x85`);
- uses the approximately 300 ms inter-write/settings verification delay seen in
  captures; and
- preserves the unknown mower-setting bit by reading it before a partial
  settings update;
- acquires the negotiated BlueZ MTU when Bleak exposes that backend operation;
  and
- reads the mower's HCI-confirmed standard Device Information characteristics
  in a single connection.

These are static-analysis and capture-informed implementation decisions. They
do not claim that REA executed the app or observed mower runtime behavior.
