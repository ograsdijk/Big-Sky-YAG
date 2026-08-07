# Big Sky YAG

Python interface for a Big Sky Laser BSS Q-switched YAG laser power supply.

> [!WARNING]
> This package controls hazardous laser hardware. Software validation does not
> replace physical interlocks, protective equipment, training, or an approved
> operating procedure. Confirm that the optical area is safe before enabling the
> flashlamp, Q-switch, or shutter.

## Installation

Big Sky YAG requires Python 3.11 through 3.14.

```bash
pip install big-sky-yag
```

## Basic operation

The controller uses a serial connection. The defaults are 9600 baud with two-second
read and write timeouts. `port` is the canonical PySerial parameter name, so the
positional `BigSkyYag("COM4")` form is equivalent to
`BigSkyYag(port="COM4")`. The former `resource_name="COM4"` keyword remains
available as a compatibility alias.

```python
import time

from big_sky_yag import BigSkyYag

with BigSkyYag("COM4") as yag:
    # Configure the laser while it is stopped.
    yag.flashlamp.frequency = 10.0  # Hz
    yag.flashlamp.voltage = 900  # V
    yag.qswitch.delay = 150  # microseconds

    # Start cooling and allow flow to establish before firing. The tested system
    # takes approximately two seconds; follow the procedure for your installation.
    yag.pump = True
    time.sleep(2.0)

    print(yag.laser_status)
    print(yag.flashlamp.interlock)
    print(yag.qswitch.interlock)

    try:
        # arm() starts the flashlamp and Q-switch, opens the shutter, and verifies
        # those three reported states. It does not start the pump or independently
        # decide whether every site-specific operating prerequisite is satisfied.
        yag.arm(timeout_s=2.0)

        # Perform the experiment here.
    finally:
        # disarm() closes the shutter, stops the Q-switch and flashlamp, and
        # positively verifies their stopped/closed states.
        yag.disarm(timeout_s=2.0)
        yag.pump = False
```

The context manager closes serial connections created by `BigSkyYag`. When an
instrument is injected for testing or integration, its owner remains responsible
for closing it.

You can also construct the device explicitly, as in earlier releases. Call
`close()` when finished so the serial port is released:

```python
from big_sky_yag import BigSkyYag

yag = BigSkyYag("COM4")
try:
    print(yag.laser_status)
    # Configure and operate the laser here.
finally:
    yag.close()
```

Test and integration transports can be injected without supplying a dummy port:

```python
yag = BigSkyYag(instrument=my_instrument)
```

## Trigger and firing modes

Use enums for statically typed configuration:

```python
from big_sky_yag import QSwitchMode, Trigger

yag.flashlamp.trigger = Trigger.INTERNAL
yag.flashlamp.trigger = Trigger.EXTERNAL

yag.qswitch.mode = QSwitchMode.AUTO
yag.qswitch.mode = QSwitchMode.BURST
yag.qswitch.mode = QSwitchMode.EXTERNAL
```

Configure the burst pulse count before selecting burst mode:

```python
yag.qswitch.pulses = 10
yag.qswitch.mode = QSwitchMode.BURST
```

## Common properties and commands

| API | Type/units | Access | Controller range |
|---|---|---|---|
| `yag.temperature_cooling_group` | `float`, °C | read | controller-defined |
| `yag.flashlamp.voltage` | `int`, V | read/write | 500–1800 |
| `yag.flashlamp.energy` | `float`, J | read/write | 7.0–23.0 |
| `yag.flashlamp.capacitance` | `float`, µF | read/write | 27.0–33.0 |
| `yag.flashlamp.frequency` | `float`, Hz | read/write | 1.00–99.99 |
| `yag.qswitch.frequency_divider` | `int`, F/n | read/write | 1–99 |
| `yag.qswitch.pulses` | `int` | read/write | 1–999 |
| `yag.qswitch.delay` | `int`, µs | read/write | 100–999 plus factory limits |
| `yag.qswitch.pulses_wait` | `int` | read | controller-defined |

Additional operations:

```python
yag.save()
serial_number = yag.serial_number

lamp_total = yag.flashlamp.counter
lamp_user = yag.flashlamp.user_counter
yag.flashlamp.user_counter_reset()

qswitch_total = yag.qswitch.counter
qswitch_user = yag.qswitch.counter_user

yag.qswitch.single()
```

## Status, interlocks, and failures

`yag.laser_status` returns an immutable `LaserStatus` snapshot. Its
`flashlamp_running` and `qswitch_running` convenience properties are true only for
continuous `START` operation, not a single-shot state.

The `IF`, `IF2`, and `IQ` interlock registers on the tested controller use a
one-deep snapshot-on-read buffer. The library reads each register twice and uses
the second response so callers receive the current sample.

The public exception hierarchy is:

- `BigSkyYagError`: base library runtime error.
- `LaserTransportError`: incomplete or undecodable serial data.
- `LaserProtocolError`: a controller reply has an unknown or invalid shape.
- `LaserTransitionError`: an arm/disarm state could not be positively verified.

Unknown responses are never interpreted as a closed shutter or another safe
state. `arm()` attempts a verified disarm if arming fails. If both operations fail,
the exception chain preserves both failures.

## Protocol notes

- Commands are terminated with `CRLF`.
- With no serial-number address, the library uses the controller's `>` broadcast
  prefix. Avoid a broadcast query when multiple responding controllers share the
  RS-485 bus.
- The exact numbered-address wire format still needs a real-device capture. The
  existing behavior is preserved pending that verification.
- Controller responses are ASCII fixed-width fields on the tested system. Some
  service-manual examples show inconsistent printed lengths; see the
  [command-reference transcription](https://github.com/ograsdijk/Big-Sky-YAG/blob/main/big_sky_bss_rs485_command_reference.md)
  for unresolved details.
- Instances are not designed for concurrent commands from multiple threads.

## Development

```bash
uv sync --locked --dev
uv run ruff format --check .
uv run ruff check .
uv run mypy
uv run pytest
uv build
uv run twine check dist/*
```

The test suite uses simulated transports and does not require laser hardware.
