import math
import time
from collections.abc import Callable
from types import TracebackType
from typing import Protocol, cast

import serial

from .attributes import Flashlamp, FloatProperty, LaserStatus, QSwitch, Status, Trigger
from .errors import LaserProtocolError, LaserTransitionError, LaserTransportError

__all__ = ["BigSkyYag", "LaserTransitionError", "SerialInstrument"]


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
            raise LaserTransportError(
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
            raise LaserTransportError("device response is not valid text") from exc
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

    def query(self, query: str) -> str:
        if self._serial_number is None:
            _query = f">{query}"
        elif isinstance(self._serial_number, int) and not isinstance(
            self._serial_number, bool
        ):
            _query = f"{self._serial_number}{query}"
        else:
            raise ValueError(f"Serial number is not valid, {self._serial_number}")
        self.instrument.write(_query)
        return self.read()

    def write(self, command: str) -> str:
        if self._serial_number is None:
            _command = f">{command}"
        elif isinstance(self._serial_number, int) and not isinstance(
            self._serial_number, bool
        ):
            _command = f"{self._serial_number}{command}"
        else:
            raise ValueError(f"Serial number is not valid, {self._serial_number}")

        self.instrument.write(_command)
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
            raise LaserProtocolError(f"unexpected SN response: {response!r}")
        value = response[len(prefix) :].strip()
        if not value:
            raise LaserProtocolError(f"unexpected SN response: {response!r}")
        return value

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
        raise LaserProtocolError(f"unexpected R response: {response!r}")

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
            raise LaserProtocolError(f"unexpected P response: {pump!r}")
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
            raise LaserProtocolError(f"unexpected WOR response: {status_string!r}")
        try:
            interlock, flashlamp, simmer, q_switch = (
                int(tokens[index]) for index in (1, 3, 5, 7)
            )
        except ValueError as exc:
            raise LaserProtocolError(
                f"unexpected WOR response: {status_string!r}"
            ) from exc
        if (
            interlock not in {0, 1}
            or simmer not in {0, 1}
            or flashlamp not in {0, 1, 2, 4, 5, 6}
            or q_switch not in {0, 1, 2, 4, 5, 6}
        ):
            raise LaserProtocolError(f"unexpected WOR response: {status_string!r}")

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
                    and last_status.qswitch_running is running
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
                raise LaserTransitionError(
                    f"laser did not become {'armed' if running else 'disarmed'} "
                    f"within {timeout_s:g} s ({detail})"
                ) from last_error
            time.sleep(min(poll_s, remaining_s))

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
        """Start flashlamp and Q-switch, then open and verify the shutter."""
        timeout_s = self._validate_transition_time(
            "timeout_s", timeout_s, allow_zero=True
        )
        poll_s = self._validate_transition_time("poll_s", poll_s, allow_zero=False)
        try:
            self.flashlamp.activate()
            self.qswitch.start()
            self.shutter = True
            self._wait_for_operational_state(
                running=True, timeout_s=timeout_s, poll_s=poll_s
            )
        except Exception as arm_error:
            try:
                self.disarm(timeout_s=timeout_s, poll_s=poll_s)
            except Exception as rollback_error:
                raise LaserTransitionError(
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
                raise LaserTransitionError(
                    "laser disarm commands failed and safe state was not verified"
                ) from ExceptionGroup(
                    "laser disarm failures", [*command_errors, verification_error]
                )
            raise
