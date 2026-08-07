import math
import time
from collections.abc import Callable
from types import TracebackType
from typing import Protocol, cast

import serial

from .attributes import Flashlamp, FloatProperty, LaserStatus, QSwitch, Status, Trigger
from .errors import (
    BigSkyYagProtocolError,
    BigSkyYagTransitionError,
    BigSkyYagTransportError,
)

__all__ = ["BigSkyYag", "BigSkyYagTransitionError", "SerialInstrument"]


class Instrument(Protocol):
    def read(self) -> bytes: ...

    def write(self, message: str) -> None: ...


class SerialInstrument:
    def __init__(
        self,
        port: str,
        baud_rate: int = 9600,
        timeout: float | None = 2.0,
        write_timeout: float | None = 2.0,
        encoding: str = "ascii",
    ) -> None:
        self._serial = serial.Serial(
            port=port,
            baudrate=baud_rate,
            timeout=timeout,
            write_timeout=write_timeout,
        )
        self._encoding = encoding

    def read(self) -> bytes:
        # All device responses are exactly 17 bytes: \r\n + 15 bytes of data.
        response = cast(bytes, self._serial.read(17))
        if len(response) != 17:
            raise BigSkyYagTransportError(
                "incomplete device response: expected 17 bytes, "
                f"received {len(response)}"
            )
        return response

    def write(self, message: str) -> None:
        # Discard any stale/late-arriving bytes from a previous command so the
        # following read is aligned with this command's response. An invalid,
        # unsupported, or timed-out command may otherwise shift the next fixed
        # 17-byte read.
        self._serial.reset_input_buffer()
        # Device requires \r\n line termination to process commands.
        self._serial.write((message + "\r\n").encode(self._encoding))

    def close(self) -> None:
        self._serial.close()


class BigSkyYag:
    temperature_cooling_group = FloatProperty(
        name="temperature cooling group in C",
        command="CG",
        ret_string="temp. CG -- d  ",
    )
    temperature_cooling_group_fahrenheit = FloatProperty(
        name="temperature cooling group in F",
        command="CGF",
        ret_string="temp. CG --- F ",
    )

    def __init__(
        self,
        port: str | None = None,
        baud_rate: int = 9600,
        serial_number: int | None = None,
        instrument: Instrument | None = None,
        timeout: float | None = 2.0,
        write_timeout: float | None = 2.0,
        encoding: str = "ascii",
        *,
        resource_name: str | None = None,
    ) -> None:
        if port is not None and resource_name is not None:
            raise ValueError("specify either port or resource_name, not both")
        resolved_port = port if port is not None else resource_name
        self._owns_instrument = instrument is None
        if instrument is None:
            if resolved_port is None:
                raise ValueError("port is required when instrument is not provided")
            self.instrument: Instrument = SerialInstrument(
                port=resolved_port,
                baud_rate=baud_rate,
                timeout=timeout,
                write_timeout=write_timeout,
                encoding=encoding,
            )
        else:
            self.instrument = instrument
        self._encoding = encoding
        self._serial_number = serial_number
        self.flashlamp = Flashlamp(self)
        self.qswitch = QSwitch(self)

    def read(self) -> str:
        try:
            message = self.instrument.read().decode(self._encoding)
        except UnicodeDecodeError as exc:
            raise BigSkyYagTransportError("device response is not valid text") from exc
        return message.strip("\r\n")

    def close(self) -> None:
        """Close the serial transport created by this instance."""
        if self._owns_instrument:
            cast(SerialInstrument, self.instrument).close()

    def __enter__(self) -> "BigSkyYag":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def _format_command(self, payload: str) -> str:
        """Prefix a command with its addressing header.

        With no serial number the controller's `>` broadcast prefix is used.
        With a serial number the addressed form is `$xxx`, a literal `$`
        followed by the three-digit zero-padded serial number (hardware
        verified: `$062...` is answered while `062...`/`62...`/`>062...` are
        not). The unprefixed decimal form used previously produced no reply.
        """
        if self._serial_number is None:
            return f">{payload}"
        if isinstance(self._serial_number, int) and not isinstance(
            self._serial_number, bool
        ):
            if not 0 <= self._serial_number <= 999:
                raise ValueError(f"Serial number is not valid, {self._serial_number}")
            return f"${self._serial_number:03d}{payload}"
        raise ValueError(f"Serial number is not valid, {self._serial_number}")

    def query(self, query: str) -> str:
        self.instrument.write(self._format_command(query))
        return self.read()

    def write(self, command: str) -> str:
        self.instrument.write(self._format_command(command))
        return self.read()

    def save(self) -> None:
        """
        Save the current configuration.
        """
        self.write("SAV1")

    @property
    def serial_number(self) -> str:
        """
        Get the device serial number.

        Returns:
            str: serial number
        """
        response = self.query("SN")
        prefix = "s/number"
        if not response.casefold().startswith(prefix):
            raise BigSkyYagProtocolError(f"unexpected SN response: {response!r}")
        value = response[len(prefix) :].strip()
        if not value:
            raise BigSkyYagProtocolError(f"unexpected SN response: {response!r}")
        return value

    @property
    def software_revision(self) -> str:
        """Controller software revision string (`X`), e.g. `SPECTRA-SY 3.68`."""
        response = self.query("X")
        value = response.strip()
        if not value:
            raise BigSkyYagProtocolError(f"unexpected X response: {response!r}")
        return value

    @property
    def software_revision_date(self) -> str:
        """Controller software revision date (`DAT`) as `dd/mm/yy`."""
        response = self.query("DAT")
        value = response.strip()
        parts = value.split("/")
        if len(parts) != 3 or not all(part.isdigit() for part in parts):
            raise BigSkyYagProtocolError(f"unexpected DAT response: {response!r}")
        return value

    @property
    def operating_time(self) -> str:
        """Operating-time counter (`T`) as `hhhh:mm`."""
        response = self.query("T")
        prefix = "ct time"
        if not response.startswith(prefix):
            raise BigSkyYagProtocolError(f"unexpected T response: {response!r}")
        value = response[len(prefix) :].strip()
        hours, _, minutes = value.partition(":")
        if not hours.isdigit() or not minutes.isdigit():
            raise BigSkyYagProtocolError(f"unexpected T response: {response!r}")
        return value

    @property
    def hg_temperature_ok(self) -> bool:
        """HG temperature test (`IHG`); True when the final status digit is `0`."""
        response = self.query("IHG")
        if not response.startswith("IHG") or not response.strip()[-1:].isdigit():
            raise BigSkyYagProtocolError(f"unexpected IHG response: {response!r}")
        return response.strip()[-1] == "0"

    @property
    def shutter_at_run(self) -> bool:
        """Whether the shutter opens automatically at run (`ROF`)."""
        response = self.query("ROF")
        prefix = "shutt. at run"
        field = ""
        if response.startswith(prefix):
            field = response.removeprefix(prefix).strip()
        if field not in {"0", "1"}:
            raise BigSkyYagProtocolError(f"unexpected ROF response: {response!r}")
        return field == "1"

    @shutter_at_run.setter
    def shutter_at_run(self, state: bool) -> None:
        if not isinstance(state, bool):
            raise TypeError(f"state not boolean but {type(state)}")
        self.write(f"ROF{state:b}")

    @property
    def echo(self) -> bool:
        """Reply/echo mode (`ECH`); True when the controller sends replies.

        Note: no reply is available when replies are already disabled, so this
        read will time out (raising a transport error) in that state.
        """
        response = self.query("ECH")
        field = response.strip()
        if field.startswith("echo on"):
            return True
        if field.startswith("echo off"):
            return False
        raise BigSkyYagProtocolError(f"unexpected ECH response: {response!r}")

    def set_echo(self, enabled: bool) -> None:
        """Enable or disable controller replies (`ECH1`/`ECH0`).

        WARNING: `ECH0` disables *all* replies while commands still execute, so
        the controller stops answering queries until `ECH1` is sent. Because the
        disable command itself produces no reply, it is written without waiting
        for a response. Use with care on a shared RS-485 bus.
        """
        if not isinstance(enabled, bool):
            raise TypeError(f"enabled not boolean but {type(enabled)}")
        if enabled:
            self.write("ECH1")
        else:
            # ECH0 produces no reply; do not attempt the fixed-frame read.
            self.instrument.write(self._format_command("ECH0"))

    @property
    def shutter(self) -> bool:
        """
        Device shutter state, True if open False if closed

        Returns:
            bool: shutter state
        """
        response = self.query("R")
        if response.strip() == "shutter opened":
            return True
        if response.strip() == "shutter closed":
            return False
        raise BigSkyYagProtocolError(f"unexpected R response: {response!r}")

    @shutter.setter
    def shutter(self, state: bool) -> None:
        """
        Open or close the shutter, with open (True) or close (False)

        Args:
            state (bool): True (open) or False (close)

        Raises:
            TypeError: raise error if state is not boolean
        """
        if not isinstance(state, bool):
            raise TypeError(f"state not boolean but {type(state)}")
        self.write(f"R{state:b}")

    @property
    def pump(self) -> bool:
        """
        Get the pump state.

        Returns:
            bool: True if on, False if off
        """
        pump = self.query("P")
        tokens = pump.split()
        if (
            len(tokens) != 3
            or tokens[:2] != ["CG", "pump"]
            or tokens[2]
            not in {
                "0",
                "1",
            }
        ):
            raise BigSkyYagProtocolError(f"unexpected P response: {pump!r}")
        return tokens[2] == "1"

    @pump.setter
    def pump(self, state: bool) -> None:
        """
        Set the pump state, either on (True) or off (False)

        Args:
            state (bool): True (on) or False (off)

        Raises:
            TypeError: raised if state is not boolean
        """
        if not isinstance(state, bool):
            raise TypeError(f"state not boolean but {type(state)}")
        self.write(f"P{state:b}")

    @property
    def laser_status(self) -> LaserStatus:
        status_string = self.query("WOR")
        tokens = status_string.split()
        if (
            len(tokens) != 8
            or tokens[0] != "I"
            or tokens[6] != "Q"
            or any(
                len(tokens[index]) != 1 or not tokens[index].isalpha()
                for index in (2, 4)
            )
        ):
            raise BigSkyYagProtocolError(f"unexpected WOR response: {status_string!r}")
        try:
            interlock, flashlamp, simmer, q_switch = (
                int(tokens[index]) for index in (1, 3, 5, 7)
            )
        except ValueError as exc:
            raise BigSkyYagProtocolError(
                f"unexpected WOR response: {status_string!r}"
            ) from exc
        if (
            interlock not in {0, 1}
            or simmer not in {0, 1}
            or flashlamp not in {0, 1, 2, 4, 5, 6}
            or q_switch not in {0, 1, 2, 4, 5, 6}
        ):
            raise BigSkyYagProtocolError(f"unexpected WOR response: {status_string!r}")

        flashlamp_state = Status(flashlamp if flashlamp < 4 else flashlamp - 4)
        qswitch_state = Status(q_switch if q_switch < 4 else q_switch - 4)

        return LaserStatus(
            interlock=interlock == 0,
            flashlamp=flashlamp_state,
            flashlamp_synchronization=(
                Trigger.INTERNAL if flashlamp <= 3 else Trigger.EXTERNAL
            ),
            simmer=bool(simmer),
            q_switch=qswitch_state,
            q_switch_synchronization=(
                Trigger.INTERNAL if q_switch <= 3 else Trigger.EXTERNAL
            ),
        )

    def _wait_for_operational_state(
        self,
        *,
        running: bool,
        timeout_s: float,
        poll_s: float,
    ) -> None:
        timeout_s = self._validate_transition_time(
            "timeout_s", timeout_s, allow_zero=True
        )
        poll_s = self._validate_transition_time("poll_s", poll_s, allow_zero=False)
        deadline = time.monotonic() + timeout_s
        last_status: LaserStatus | None = None
        last_shutter: bool | None = None
        last_error: Exception | None = None
        while True:
            try:
                last_status = self.laser_status
                last_shutter = self.shutter
                if (
                    last_status.flashlamp_running is running
                    and self._qswitch_state_reached(last_status, running=running)
                    and last_shutter is running
                ):
                    return
                last_error = None
            except Exception as exc:
                last_error = exc

            remaining_s = deadline - time.monotonic()
            if remaining_s <= 0:
                detail = (
                    f"status={last_status!r}, shutter={last_shutter!r}, "
                    f"last_error={last_error!r}"
                )
                raise BigSkyYagTransitionError(
                    f"laser did not become {'armed' if running else 'disarmed'} "
                    f"within {timeout_s:g} s ({detail})"
                ) from last_error
            time.sleep(min(poll_s, remaining_s))

    @staticmethod
    def _qswitch_state_reached(status: LaserStatus, *, running: bool) -> bool:
        """Whether the Q-switch has reached the target arm/disarm state.

        An externally-triggered Q-switch never reports continuous ``Start`` via
        ``WOR``; it idles at the external ``Stop`` code while awaiting external
        triggers (hardware verified 2026-08-07). So when *arming* with the
        Q-switch in external synchronization there is no positive ``Start`` to
        confirm — the flashlamp ``Start`` and open shutter remain positively
        verified. When *disarming*, the stopped state is still confirmed in both
        modes.
        """
        if running and status.q_switch_synchronization is Trigger.EXTERNAL:
            return True
        return status.qswitch_running is running

    @staticmethod
    def _validate_transition_time(
        name: str, value: float, *, allow_zero: bool
    ) -> float:
        try:
            parsed = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{name} must be a finite number") from exc
        if not math.isfinite(parsed) or parsed < 0 or (parsed == 0 and not allow_zero):
            qualifier = "non-negative" if allow_zero else "positive"
            raise ValueError(f"{name} must be a finite {qualifier} number")
        return parsed

    def arm(self, *, timeout_s: float = 2.0, poll_s: float = 0.1) -> None:
        """Start flashlamp and Q-switch, then open and verify the shutter.

        Verification requires the flashlamp to report continuous ``Start`` and
        the shutter to report open. The Q-switch is also required to report
        ``Start`` when it is in internal synchronization; in external
        synchronization it idles awaiting external triggers and never reports
        ``Start``, so that condition is not required (the flashlamp and shutter
        remain positively verified).
        """
        timeout_s = self._validate_transition_time(
            "timeout_s", timeout_s, allow_zero=True
        )
        poll_s = self._validate_transition_time("poll_s", poll_s, allow_zero=False)
        try:
            self.flashlamp.activate()
            self.shutter = True
            self.qswitch.start()
            self._wait_for_operational_state(
                running=True, timeout_s=timeout_s, poll_s=poll_s
            )
        except Exception as arm_error:
            try:
                self.disarm(timeout_s=timeout_s, poll_s=poll_s)
            except Exception as rollback_error:
                raise BigSkyYagTransitionError(
                    "laser arm failed and rollback could not verify a safe state"
                ) from ExceptionGroup(
                    "laser arm and rollback failures", [arm_error, rollback_error]
                )
            raise

    def disarm(self, *, timeout_s: float = 2.0, poll_s: float = 0.1) -> None:
        """Close shutter and stop Q-switch/flashlamp, then verify all are off."""
        timeout_s = self._validate_transition_time(
            "timeout_s", timeout_s, allow_zero=True
        )
        poll_s = self._validate_transition_time("poll_s", poll_s, allow_zero=False)
        command_errors: list[Exception] = []

        def close_shutter() -> None:
            self.shutter = False

        commands: tuple[Callable[[], None], ...] = (
            close_shutter,
            self.qswitch.stop,
            self.flashlamp.stop,
        )
        for command in commands:
            try:
                command()
            except Exception as exc:
                command_errors.append(exc)

        try:
            self._wait_for_operational_state(
                running=False, timeout_s=timeout_s, poll_s=poll_s
            )
        except Exception as verification_error:
            if command_errors:
                raise BigSkyYagTransitionError(
                    "laser disarm commands failed and safe state was not verified"
                ) from ExceptionGroup(
                    "laser disarm failures", [*command_errors, verification_error]
                )
            raise
