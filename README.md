# pyGrouw

Python library for local Bluetooth Low Energy communication with Grouw robotic
mowers. It supports both the legacy DYM generation and the newer JSON-over-BLE
generation used by Robotic Mower Connect.

This package contains the device/protocol code intended to be used by Home
Assistant integrations and other Python applications. It has no Home Assistant
runtime dependency.

## Status

The legacy DYM path is informed by app analysis and redacted real-hardware
captures. The newer Connect path was statically recovered from Robotic Mower
Connect 1.4.5 and has not yet been validated against physical hardware.

Durable protocol and reverse-engineering notes live in
[reverse_engineered/index.md](reverse_engineered/index.md).

Supported protocol helpers:

- DYM status, start/resume, pause/stop, dock, session start, and auth query
  payload encoding.
- DYM manual driving, blade control, force stop, clock, language, alert, and
  runtime commands and response parsing.
- DYM PIN changes, mower settings, multi-area settings, and weekly work-time
  query/write helpers with read-back verification.
- Connect A4/length/XOR framing and fragmented notification reassembly for the
  FFF0 service with FFF1 notify and FFF2 write characteristics.
- Connect status, device information, battery information, feature flags, rain,
  multi-area, and schedule queries.
- Connect work/stop/home/trim/start-point control plus rain, ultrasonic,
  language, PIN, clock, device name, Wi-Fi provisioning, LED, multi-area, and
  schedule setters, GPS/electronic-feature control, PIN verification, map reset,
  and device reset.
- Standard GATT Device Information reads for model, serial, firmware, hardware,
  software, manufacturer, and System ID fields exposed by the mower.
- APK-shaped BlueKey debug payload encoding and parsing helpers for protocol
  research.
- Optional BLE discovery helpers that match the Home Assistant integration's
  supported name/service UUID filters.
- Serialized BLE request flow using `bleak` and `bleak-retry-connector`.

Additional protocol operations implemented in `GrouwBleMowerClient`:

- Read and write multi-area settings.
- Read and write mower settings including rain behavior and delay.
- Read and write work time schedules.
- Change the mower PIN (requires authenticated BLE access).

Not yet supported:

- Cloud control. Wi-Fi credential provisioning is local BLE configuration, not
  a cloud client.
- Firmware update.

## Installation For Development

```bash
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install -e .
python3 -m pip install pytest
pytest -q
```

## Usage

Applications should resolve a connectable BLE device themselves, then pass it
to the client. Home Assistant integrations should use Home Assistant's
Bluetooth manager and inject the resolved device.

```python
from pygrouw import GrouwMower, GrouwBleMowerClient

client = GrouwBleMowerClient(
    address="AA:BB:CC:DD:EE:FF",
    name="Robot Mower_DYM",
    pin="1234",
    device_provider=lambda: ble_device,
)
mower = GrouwMower(client)

state = await mower.async_update()
state = await mower.async_update_device_information()
await mower.async_start()
```

For a mower supported by Robotic Mower Connect, use the Connect client:

```python
from pygrouw import GrouwConnectBleMowerClient, GrouwMower

client = GrouwConnectBleMowerClient(
    address="AA:BB:CC:DD:EE:FF",
    name="Grouw Mower",
    pin="1234",
    device_provider=lambda: ble_device,
)
mower = GrouwMower(client)

state = await mower.async_update()
await mower.async_start()
await mower.async_trim()
await mower.async_start_at_point(2)
```

Generation-specific settings are available on the lower-level clients. For
example, `GrouwBleMowerClient` exposes DYM mower settings, multi-area, work
times, clock, language, alert, and runtime methods;
`GrouwConnectBleMowerClient` exposes Connect battery/feature/rain/schedule/
multi-area queries and its recovered local setters and reset operations. These
Connect methods are based on static APK evidence and remain hardware-unvalidated.

`async_update_device_information()` populates the model, serial number, and
firmware revision fields already present in `MowerState`. The lower-level
`client.async_get_device_information()` method returns every available standard
Device Information field.

`device_provider` may be synchronous or asynchronous. It must return a
connectable `bleak.backends.device.BLEDevice` or `None`.

For standalone scripts, the library also exposes optional discovery helpers:

```python
from pygrouw import GrouwMower, GrouwBleMowerClient, discover_devices

devices = await discover_devices(timeout=5)
client = await GrouwBleMowerClient.from_discovery(
    address=devices[0].address,
    pin="1234",
)
mower = GrouwMower(client)

state = await mower.async_update()
```

Home Assistant integrations should still prefer Home Assistant's Bluetooth
manager over calling these scanning helpers from inside Home Assistant.

## Home Assistant Development

When testing an unpublished editable library inside Home Assistant:

```bash
pip3 install -e ../pyGrouw
hass --skip-pip-packages pygrouw
```

That follows Home Assistant's guidance for standalone API/protocol libraries:
protocol-specific code lives outside the integration and package releases are
eventually published to PyPI from tagged source releases.

## Release Publishing

GitHub Actions runs tests for pull requests and pushes to `main`. Published
GitHub releases also run the full test/build/check flow before uploading to
PyPI.

PyPI publishing is configured for Trusted Publishing. On PyPI, create a
Trusted Publisher for this project with:

- Repository owner: `Bjorkan`
- Repository name: `pyGrouw`
- Workflow name: `publish.yml`
- Environment name: `pypi`

If `pygrouw` does not exist on PyPI yet, create a pending publisher from your
PyPI account sidebar under **Publishing**. If the project already exists, open
the project on PyPI, go to **Manage project** -> **Publishing**, and add the
GitHub Actions publisher there.

Before publishing a release, update `version` in `pyproject.toml`, merge to
`main`, create a matching tag, and publish a GitHub Release from that tag. The
publish workflow requires the release tag to match the package version, with or
without a `v` prefix. For version `0.1.0`, both `0.1.0` and `v0.1.0` are valid.

## Dependency Updates

Renovate is configured in `renovate.json`. The GitHub workflow runs Renovate
at `00:00` UTC, and can also be started manually from the Actions tab.

Add a repository secret named `RENOVATE_TOKEN` with permission to create
branches and pull requests. Do not use the default `GITHUB_TOKEN` for Renovate:
pull requests created with it do not reliably trigger the normal PR checks.
