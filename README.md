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

Supported and experimental capabilities:

| Feature | Read | Write | Evidence | Stability |
| --- | --- | --- | --- | --- |
| Status, battery, mode, station | Yes | N/A | Hardware capture | Supported |
| Start, resume, pause, dock | Status follow-up | Yes | Hardware capture | Experimental; transport completion is not physical-state confirmation |
| Multi-area settings | Yes | Yes | Hardware capture | Experimental; writes use read-back verification |
| Mower settings | Yes | Yes | Partial hardware capture | Experimental; omitted unknown fields are preserved |
| Weekly work times | Yes | Yes | Hardware capture | Experimental; writes follow captured 300 ms spacing |
| PIN change | Yes | Yes | Hardware capture | Experimental; interrupted verification can leave an indeterminate result |
| BlueKey helpers | Research only | Research only | APK-derived | Debug/reverse-engineering only |
| Firmware update | No | No | Unknown | Unsupported |
| Cloud or Wi-Fi control | No | No | Not applicable | Unsupported |

All BLE requests are serialized. A completed GATT write or a later status response
proves communication, but does not by itself prove that a physical mower action has
completed. `async_command_result()` exposes this distinction explicitly. Multi-step
writes may raise `GrouwBleOperationIndeterminate` when an earlier step could already
have changed the mower; callers should read back state before retrying.

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
from pygrouw import GrouwBleMower, GrouwBleMowerClient

client = GrouwBleMowerClient(
    address="AA:BB:CC:DD:EE:FF",
    name="Robot Mower_DYM",
    pin="1234",
    device_provider=lambda: ble_device,
)
mower = GrouwMower(client)

state = await mower.async_update()
await mower.async_start()
```

`device_provider` may be synchronous or asynchronous. It must return a
connectable `bleak.backends.device.BLEDevice` or `None`.

For standalone scripts, the library also exposes optional discovery helpers:

```python
from pygrouw import GrouwBleMower, GrouwBleMowerClient, discover_devices

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
