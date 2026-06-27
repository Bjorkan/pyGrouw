# pyGrouw

Python library for local Bluetooth Low Energy communication with Grouw robotic
mowers that use the Daye Power app protocol (`com.dayepower.dayeappleaf`).

This package contains the device/protocol code intended to be used by Home
Assistant integrations and other Python applications. It has no Home Assistant
runtime dependency.

## Status

The library currently targets the DYM-era Grouw mower generation observed in
the Daye Power APK and redacted real-hardware captures.

Durable protocol and reverse-engineering notes live in
[reverse_engineered/index.md](reverse_engineered/index.md).

Supported protocol helpers:

- DYM status, start/resume, pause/stop, dock, session start, and auth query
  payload encoding.
- DYM status and auth/PIN notification parsing.
- APK-shaped BlueKey debug payload encoding and parsing helpers for protocol
  research.
- Serialized BLE request flow using `bleak` and `bleak-retry-connector`.

Not yet supported:

- Cloud or Wi-Fi control.
- BLE scanning as a public API.
- Settings writes for rain, schedules, multi-area, PIN change, or firmware
  update.

## Installation For Development

```bash
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install -e ".[test]"
pytest -q
```

## Usage

Applications should resolve a connectable BLE device themselves, then pass it
to the client. Home Assistant integrations should use Home Assistant's
Bluetooth manager and inject the resolved device.

```python
from pygrouw import GrouwBleMowerClient

client = GrouwBleMowerClient(
    address="AA:BB:CC:DD:EE:FF",
    name="Robot Mower_DYM",
    pin="1234",
    device_provider=lambda: ble_device,
)

status = await client.async_get_all_info()
await client.async_command("start")
```

`device_provider` may be synchronous or asynchronous. It must return a
connectable `bleak.backends.device.BLEDevice` or `None`.

## Home Assistant Development

When testing an unpublished editable library inside Home Assistant:

```bash
pip3 install -e ../pyGrouw
hass --skip-pip-packages pygrouw
```

That follows Home Assistant's guidance for standalone API/protocol libraries:
protocol-specific code lives outside the integration and package releases are
eventually published to PyPI from tagged source releases.
