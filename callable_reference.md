# pyGrouw Callable Reference

This is a short reference for developers who import `pyGrouw` into their own codebase.

It lists the main things you can call from an app or integration, such as reading mower status, sending commands, changing PIN, and updating mower settings.

## Basic import

```python
from pygrouw import GrouwBleMowerClient
from pygrouw.discovery import discover_devices, find_device_by_address
```

Most methods are async and must be called with `await`.

---

## Create a client

### `GrouwBleMowerClient.from_discovery(address, pin, timeout=5.0)`

Scans for the mower and returns a ready-to-use client.

```python
client = await GrouwBleMowerClient.from_discovery(
    "AA:BB:CC:DD:EE:FF",
    pin="1234",
)
```

### `GrouwBleMowerClient(address, name=None, pin="", device=None, device_provider=None)`

Creates a client manually if your app already has a BLE device object.

```python
client = GrouwBleMowerClient(
    address="AA:BB:CC:DD:EE:FF",
    pin="1234",
    device=device,
)
```

Use this style if your app or framework already manages Bluetooth discovery.

---

## Discovery

### `discover_devices(timeout=5.0)`

Scans for supported Grouw/Daye BLE mowers.

```python
mowers = await discover_devices(timeout=5.0)

for mower in mowers:
    print(mower.name, mower.address, mower.rssi)
```

### `find_device_by_address(address, timeout=5.0)`

Finds a specific BLE device by address.

```python
device = await find_device_by_address("AA:BB:CC:DD:EE:FF")
```

### `is_valid_pin(pin)`

Checks if a PIN is exactly four decimal digits.

```python
is_valid_pin("1234")  # True
```

### `normalize_address(address)`

Normalizes a Bluetooth address.

```python
normalize_address("aa:bb:cc:dd:ee:ff")
# "AA:BB:CC:DD:EE:FF"
```

---

## Status

### `client.async_get_all_info()`

Reads mower status.

```python
status = await client.async_get_all_info()
```

Common response fields:

```python
status["battery_level"]
status["mode"]
status["station"]
status["raw_hex"]
```

Example:

```python
status = await client.async_get_all_info()

print("Battery:", status.get("battery_level"))
print("Mode:", status.get("mode"))
print("Docked:", status.get("station"))
```

---

## Mower commands

### `client.async_command("start")`

Starts mowing.

```python
await client.async_command("start")
```

### `client.async_command("pause")`

Pauses mowing.

```python
await client.async_command("pause")
```

### `client.async_command("resume")`

Resumes mowing.

```python
await client.async_command("resume")
```

### `client.async_command("dock")`

Sends the mower back to the charging station.

```python
await client.async_command("dock")
```

---

## PIN

### `client.async_change_pin(new_pin, old_pin=None)`

Changes the mower PIN.

```python
await client.async_change_pin("4321")
```

Or with the old PIN explicitly provided:

```python
await client.async_change_pin(
    old_pin="1234",
    new_pin="4321",
)
```

After a successful change, the client updates `client.pin` to the new PIN.

Your app should also save the new PIN in its own config or storage.

---

## Multi-area / multi-start points

### `client.async_get_multi_area()`

Reads the multi-area settings.

```python
response = await client.async_get_multi_area()
multi_area = response["multi_area"]
```

Common fields:

```python
multi_area["area2_percentage"]
multi_area["area2_distance"]
multi_area["area3_percentage"]
multi_area["area3_distance"]
```

### `client.async_set_multi_area(...)`

Writes and verifies multi-area settings.

```python
await client.async_set_multi_area(
    area2_percentage=5,
    area2_distance=12,
    area3_percentage=16,
    area3_distance=74,
)
```

Reset all values to zero:

```python
await client.async_set_multi_area(
    area2_percentage=0,
    area2_distance=0,
    area3_percentage=0,
    area3_distance=0,
)
```

---

## Mower settings

### `client.async_get_mower_settings()`

Reads mower settings.

```python
response = await client.async_get_mower_settings()
settings = response["mower_settings"]
```

Common fields:

```python
settings["mow_in_rain"]
settings["boundary_cut"]
settings["unknown_setting"]
settings["helix"]
settings["rain_delay_hour"]
settings["rain_delay_minute"]
settings["led"]
```

### `client.async_set_mower_settings(...)`

Writes and verifies mower settings.

```python
await client.async_set_mower_settings(
    mow_in_rain=True,
    boundary_cut=False,
    helix=True,
    rain_delay_hours=4,
    rain_delay_minutes=13,
)
```

With the unknown setting byte exposed:

```python
await client.async_set_mower_settings(
    mow_in_rain=True,
    boundary_cut=False,
    unknown_setting=False,
    helix=True,
    rain_delay_hours=4,
    rain_delay_minutes=13,
)
```

Parameters:

```text
mow_in_rain         bool
boundary_cut        bool
unknown_setting     bool, optional
helix               bool
rain_delay_hours    0..23
rain_delay_minutes  0..59
```

---

## Work time schedule

### `client.async_get_work_times()`

Reads the weekly work time schedule.

```python
work_times = await client.async_get_work_times()
```

Response fields:

```python
work_times["work_time_starts"]
work_times["work_time_durations"]
```

Example start entry:

```python
{"day": "monday", "hour": 18, "minute": 0}
```

Example duration entry:

```python
{"day": "monday", "hours": 1, "tenths": 0}
```

### `client.async_set_work_times(starts, durations)`

Writes and verifies the weekly work time schedule.

Day order is always:

```text
monday, tuesday, wednesday, thursday, friday, saturday, sunday
```

Example:

```python
starts = [
    (18, 0),
    (11, 13),
    (11, 21),
    (4, 7),
    (18, 0),
    (10, 1),
    (17, 50),
]

durations = [
    (1, 0),
    (11, 9),
    (10, 0),
    (3, 0),
    (4, 0),
    (2, 0),
    (6, 0),
]

await client.async_set_work_times(starts, durations)
```

Format:

```text
starts     list of (hour, minute)
durations  list of (whole_hours, tenths)
```

---

## Raw/debug calls

### `client.async_send_raw_json(payload)`

Sends a raw or debug payload.

Use this for debugging, custom protocol testing, or Home Assistant service calls.

Named command:

```python
response = await client.async_send_raw_json({
    "command": "status",
    "expect_cmd": 0x80,
    "authenticate": False,
})
```

Raw hex:

```python
response = await client.async_send_raw_json({
    "raw_hex": "44594d00111111111111111100000000000000160601ff0a",
    "expect_cmd": 0x80,
    "authenticate": False,
})
```

---

## Low-level protocol helpers

These are mainly useful for tests, debugging, or custom integrations.

### `encode_daye_command(command)`

Builds a Daye command payload.

```python
encode_daye_command("status")
encode_daye_command("start")
encode_daye_command("pause")
encode_daye_command("resume")
encode_daye_command("dock")
encode_daye_command("auth_query")
```

### `encode_daye_change_pin(old_pin, new_pin)`

Builds the PIN change payload.

```python
payload = encode_daye_change_pin("1234", "4321")
```

### `encode_daye_multi_area(...)`

Builds a multi-area write payload.

```python
payload = encode_daye_multi_area(
    area2_percentage=5,
    area2_distance=12,
    area3_percentage=16,
    area3_distance=74,
)
```

### `encode_daye_mower_settings(...)`

Builds a mower settings write payload.

```python
payload = encode_daye_mower_settings(
    mow_in_rain=True,
    boundary_cut=False,
    helix=True,
    rain_delay_hours=4,
    rain_delay_minutes=13,
)
```

### `encode_daye_work_time_starts(starts)`

Builds the work-time start payload.

```python
payload = encode_daye_work_time_starts([
    (18, 0), (11, 13), (11, 21), (4, 7), (18, 0), (10, 1), (17, 50)
])
```

### `encode_daye_work_time_durations(durations)`

Builds the work-time duration payload.

```python
payload = encode_daye_work_time_durations([
    (1, 0), (11, 9), (10, 0), (3, 0), (4, 0), (2, 0), (6, 0)
])
```

### `parse_daye_payload(payload)`

Parses a BLE notification payload.

```python
message = parse_daye_payload(payload)
```

### `redact_daye_message(message)`

Redacts sensitive PIN data before logging.

```python
safe_message = redact_daye_message(message)
```

### `encode_raw_payload(payload)`

Builds bytes from a JSON-like payload.

```python
payload = encode_raw_payload({"command": "status"})
payload = encode_raw_payload({"raw_hex": "44594d00..."})
```

---

## State helpers

### `state_from_message(address, message, previous=None)`

Creates or updates a `MowerState` object from a parsed response.

```python
state = state_from_message(client.address, status)
```

### `MowerState`

State object for app-level use.

```python
state.battery_level
state.mode
state.station
state.available
state.raw
```

---

## Exceptions

Common exceptions to catch in an app:

```python
GrouwBleError
GrouwBleAuthenticationError
GrouwBleConnectionError
GrouwBleDeviceNotFound
GrouwBleGattError
GrouwBleTimeout
```

Example:

```python
try:
    status = await client.async_get_all_info()
except GrouwBleAuthenticationError:
    print("Invalid PIN")
except GrouwBleTimeout:
    print("Mower did not respond in time")
except GrouwBleError as err:
    print(err)
```

---

## Quick mapping

| App action | pyGrouw call |
|---|---|
| Scan for mowers | `await discover_devices()` |
| Create client by scan | `await GrouwBleMowerClient.from_discovery(...)` |
| Read status | `await client.async_get_all_info()` |
| Start mowing | `await client.async_command("start")` |
| Pause mowing | `await client.async_command("pause")` |
| Resume mowing | `await client.async_command("resume")` |
| Dock mower | `await client.async_command("dock")` |
| Change PIN | `await client.async_change_pin(...)` |
| Read multi-area | `await client.async_get_multi_area()` |
| Set multi-area | `await client.async_set_multi_area(...)` |
| Read mower settings | `await client.async_get_mower_settings()` |
| Set mower settings | `await client.async_set_mower_settings(...)` |
| Read work times | `await client.async_get_work_times()` |
| Set work times | `await client.async_set_work_times(...)` |
| Send raw payload | `await client.async_send_raw_json(...)` |
