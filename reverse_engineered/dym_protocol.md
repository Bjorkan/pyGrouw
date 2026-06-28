# DYM Protocol

Last updated: 2026-06-26.

This file covers the HCI-confirmed 24-byte DYM protocol currently used by the
Home Assistant integration.

For APK-derived BlueKey payloads, see [bluekey_commands.md](bluekey_commands.md).

## Packet Shapes

Outbound writes are 24 bytes:

```text
byte 0..2   ASCII "DYM" prefix
byte 3      command byte
byte 4..18  command-specific data / zero padding
byte 19..23 trailer: 16 06 01 ff 0a
```

Inbound notifications observed so far are 22 bytes:

```text
byte 0..2   ASCII "DYM" prefix
byte 3      response command
byte 4..18  response data
byte 19..21 trailer: 16 06 01
```

Observed response commands:

```text
0x80 / decimal 128 = status/query response
0x8c / decimal 140 = auth/PIN response
```

## Captured Writes

```text
Status poll:
44594d00111111111111111100000000000000160601ff0a

Session/auth-related:
44594d02141a0619121c000000000000000000160601ff0a
44594d02141a06191220000000000000000000160601ff0a
44594d0c000000000000000000000000000000160601ff0a

Start mowing from dock/station:
44594d01020000000000000000000000000000160601ff0a

Resume/start after stop on lawn:
44594d01000000000000000000000000000000160601ff0a

Pause/stop:
44594d01010000000000000000000000000000160601ff0a

Go to base station:
44594d01030000000000000000000000000000160601ff0a
```

The `0x02` session payload embeds phone date/time as
`year, month, day, hour, minute`. Example: `1a 06 19 12 1c` means
2026-06-25 18:28.

The app produced two start-like writes in captures:

- `44594d0102...` when starting from dock/station.
- `44594d0100...` when resuming after a stop on the lawn.

## Auth And PIN Notes

Captured fresh app sessions send a session/authentication prelude before status
polling or commands:

1. Session payload, command `0x02`, with date/time data.
2. Auth query, command `0x0c`.
3. Auth/PIN response, response command `0x8c`.
4. Status polling or controls.

The captured DYM auth query after entering PIN `1234` contains zeros after the
command byte; the typed PIN is not visible in that write. DYM auth responses
should be treated as PIN-looking only when bytes 4-7 are four numeric digit
bytes (`0x00` through `0x09`).

The APK's BlueKey PIN flow queries the robot PIN and compares it locally in
Dart. That supports the query/compare model, but DYM auth response semantics
are not fully captured.

## Captured Status Notifications

22-byte examples:

```text
44594d8064321b000004000114444100000000160601
44594d8064321b000004000100444100000000160601
44594d8064321b000004000103444100000000160601
```

Observed field mapping:

```text
byte 0..2   "DYM"
byte 3      response command, 0x80 for status
byte 4      battery percentage candidate, observed 0x64 and 0x32
byte 7      station/docked candidate:
              0x01 = docked / at station
              0x00 = away from station
byte 12     mode candidate:
              0x00 = mowing / active
              0x01 = mowing / active, exact distinction unknown
              0x03 = returning home
              0x14 = stopped / standing still / docked / idle
byte 19..21 notification trailer: 16 06 01
```

The station byte must take precedence when mapping Home Assistant lawn mower
activity. Real hardware can report a mowing-looking mode while the station byte
reports docked.

## Home Assistant Behavior Decisions

Normal Home Assistant status polling sends the captured DYM status request
without the session/auth prelude.

Hardware validation on 2026-06-26 showed:

```text
authenticated command: status     -> beeped
unauthenticated command: status   -> quiet
unauthenticated session_start     -> two beeps, then notification timeout
unauthenticated BlueKey queryInfo -> quiet, then notification timeout
```

Normal Home Assistant commands also skip the session/auth prelude. Validation
showed unauthenticated `resume`, `dock`, and `pause` payloads execute. Direct
raw calls timed out because the mower did not send the expected command
notification, so normal command handling writes the command and then sends a
quiet DYM status request as a follow-up before waiting for state.

`resume` still produces the mower's normal three-beep manual start warning.
`dock` and `pause` did not produce extra beeps in the observed run.

## Relationship To BlueKey

DYM and BlueKey are distinct formats in the evidence we have:

| Feature | DYM | BlueKey |
| --- | --- | --- |
| Packet size | 24 bytes | 48 values |
| Prefix | ASCII `"DYM"` | `[0x88, 0xb2, 0x9a]` |
| Trailer | `16 06 01 ff 0a` | `[44, 12, 2, 510, 20]` |
| Current HA use | normal polling and controls | raw debug probes only |
| Main evidence | HCI snoop captures | Dart AOT / blutter analysis |

APK inspection showed `DeviceLogic::initDeviceInfo` sends
`BlueKey::queryInfo` with `notifyType: "0x80"`. `notifyType` is matched
against received byte index 3, so this links app-side query/info handling to
the same response-command position as DYM `0x80`.

This does not prove DYM byte 12 and BlueKey queryInfo byte13 have identical
semantics. Keep the mappings separate until paired captures prove otherwise.

## PIN Change — DYM 0x06 / 0x86

Captured on 2026-06-28 from the official Daye Power app.

### Write format (24 bytes)

```text
byte 0..2    ASCII "DYM"
byte 3       command: 0x06
byte 4..7    old PIN, one binary digit per byte
byte 8..11   new PIN, one binary digit per byte
byte 12..18  zero padding
byte 19..23  trailer: 16 06 01 ff 0a
```

### Response format (22 bytes)

```text
byte 0..2    ASCII "DYM"
byte 3       response: 0x86
byte 4..18   all-zero indicates success
byte 19..21  trailer: 16 06 01
```

### Captured test vectors

```
1234 -> 4321:
44594d06010203040403020100000000000000160601ff0a

4321 -> 1234:
44594d06040302010102030400000000000000160601ff0a
```

The official app follows a successful change with an `0x0c` auth query to verify
the new PIN against the mower's stored value.

## Multi-Area Settings — DYM 0x0d / 0x1d / 0x8d

Captured on 2026-06-28 from the official Daye Power app.

### Query format (24 bytes)

```
44594d1d000000000000000000000000000000160601ff0a
```

Command: `0x1d`. Response: `0x8d`.

### Write format (24 bytes)

```
byte 0..2    ASCII "DYM"
byte 3       command: 0x0d
byte 4       Area2_Per percentage
byte 5..7    Area2_Dis as three decimal chunk bytes
byte 8       Area3_Per percentage
byte 9..11   Area3_Dis as three decimal chunk bytes
byte 12..18  reserved / zero padding
byte 19..23  trailer: 16 06 01 ff 0a
```

Distance values use decimal chunk encoding: `00 01 02` = 12 m, `00 07 04` = 74 m.

### Captured test vectors

```
Query:
44594d1d000000000000000000000000000000160601ff0a

Set Area2=5%/12m, Area3=16%/74m:
44594d0d050001021000070400000000000000160601ff0a

Reset all zero:
44594d0d000000000000000000000000000000160601ff0a
```

No immediate DYM notification ACK was observed after `0x0d` writes.

## Mower Settings — DYM 0x09 / 0x19 / 0x89

Captured on 2026-06-28 from the official Daye Power app.

### Query format (24 bytes)

```
44594d19000000000000000000000000000000160601ff0a
```

Command: `0x19`. Response: `0x89`.

### Write format (24 bytes)

```
byte 0..2    ASCII "DYM"
byte 3       command: 0x09
byte 4       mow in rain / Klippa i regn
byte 5       boundary cut / Gränsklippning
byte 6       unknown setting (ultrasound or hidden)
byte 7       helix / Helix set
byte 8       rain delay hours
byte 9       rain delay minutes
byte 10..18  reserved / zero padding
byte 19..23  trailer: 16 06 01 ff 0a
```

### Response format (22 bytes)

```
byte 0..2    ASCII "DYM"
byte 3       0x89
byte 4       mow in rain
byte 5       boundary cut
byte 6       unknown setting
byte 7       helix
byte 8       rain delay hours
byte 9       rain delay minutes
byte 10..18  reserved
byte 19..21  trailer: 16 06 01
```

### Captured test vectors

```
Query:
44594d19000000000000000000000000000000160601ff0a

Set mow_in_rain=JA, boundary_cut=NEJ, helix=JA, delay=4h13m:
44594d0901000001040d000000000000000000160601ff0a

Set all NEJ / 0h0m:
44594d09000000000000000000000000000000160601ff0a
```

No DYM notification ACK was observed after `0x09` writes.

## Open Questions

- Exact meaning of all DYM status bytes.
- Exact distinction between DYM modes `0x00` and `0x01`.
- Whether DYM has a checksum beyond the fixed write trailer.
- Whether DYM and BlueKey are selected by firmware generation, auth state,
  native wrapping, or device type.
- Exact DYM auth response fields beyond PIN-looking bytes.
- Whether failed PIN changes return `0x86` with non-zero error bytes.
