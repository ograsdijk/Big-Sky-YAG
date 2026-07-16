import time
from collections.abc import Callable
from typing import Optional, Protocol, cast

import serial

from .attributes import Flashlamp, FloatProperty, LaserStatus, QSwitch, Status, Trigger

__all__ = ["BigSkyYag", "LaserTransitionError", "SerialInstrument"]


class LaserTransitionError(RuntimeError):
    """The laser did not reach a requested operational state."""


class Instrument(Protocol):
    def read(self) -> bytes: ...

    def write(self, message: str) -> None: ...


class SerialInstrument:
    def __init__(
        self,
        port: str,
        baud_rate: int = 9600,
        timeout: Optional[float] = 2.0,
        write_timeout: Optional[float] = 2.0,
        encoding: str = "ascii",
    ):
        self._serial = serial.Serial(
            port=port,
            baudrate=baud_rate,
            timeout=timeout,
            write_timeout=write_timeout,
        )
        self._encoding = encoding

    def read(self) -> bytes:
        # All device responses are exactly 17 bytes: \r\n + 15 bytes of data.
        return cast(bytes, self._serial.read(17))

    def write(self, message: str) -> None:
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
        resource_name: str,
        baud_rate: int = 9600,
        serial_number: Optional[int] = None,
        instrument: Optional[Instrument] = None,
        timeout: Optional[float] = 2.0,
        write_timeout: Optional[float] = 2.0,
    ):
        self.instrument = (
            instrument
            if instrument is not None
            else SerialInstrument(
                port=resource_name,
                baud_rate=baud_rate,
                timeout=timeout,
                write_timeout=write_timeout,
            )
        )
        self._serial_number = serial_number
        self.flashlamp = Flashlamp(self)
        self.qswitch = QSwitch(self)  # type: ignore[no-untyped-call]

    def read(self) -> str:
        message = self.instrument.read().decode()
        return message.strip("\r\n")

    def query(self, query: str) -> str:
        if self._serial_number is None:
            _query = f">{query}"
        elif isinstance(self._serial_number, int):
            _query = f"{self._serial_number}{query}"
        else:
            raise ValueError(f"Serial number is not valid, {self._serial_number}")
        self.instrument.write(_query)
        return self.read()

    def write(self, command: str) -> str:
        if self._serial_number is None:
            _command = f">{command}"
        elif isinstance(self._serial_number, int):
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
        return self.query("SN").replace("s/number", "").strip()

    @property
    def shutter(self) -> bool:
        """
        Device shutter state, True if open False if closed

        Returns:
            bool: shutter state
        """
        shutter = self.query("R")
        shutter = shutter.removeprefix("shutter").strip()
        return shutter == "open"

    @shutter.setter
    def shutter(self, state: bool) -> None:
        """
        Open or close the shutter, with open (True) or close (False)

        Args:
            state (str): True (open) or False (close)

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
        return bool(int(pump.split()[-1]))

    @pump.setter
    def pump(self, state: bool) -> None:
        """
        Set the pump state, either on (True) or off (False)

        Args:
            state (bool): True (on) or False (off)

        Raises:
            Type: raise error if state is not boolean
        """
        if not isinstance(state, bool):
            raise TypeError(f"state not boolean but {type(state)}")
        self.write(f"P{state:b}")

    @property
    def laser_status(self) -> LaserStatus:
        status_string = self.query("WOR")
        tokens = status_string.split()
        if len(tokens) != 8:
            raise ValueError(f"unexpected laser status response: {status_string!r}")
        try:
            interlock, flashlamp, simmer, q_switch = (
                int(tokens[index]) for index in (1, 3, 5, 7)
            )
            flashlamp_state = Status(flashlamp % 4)
            qswitch_state = Status(q_switch % 4)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"unexpected laser status response: {status_string!r}"
            ) from exc

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
        deadline = time.monotonic() + max(0.0, float(timeout_s))
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
            time.sleep(min(max(0.0, float(poll_s)), remaining_s))

    def arm(self, *, timeout_s: float = 2.0, poll_s: float = 0.1) -> None:
        """Start flashlamp and Q-switch, then open and verify the shutter."""
        try:
            self.flashlamp.activate()
            self.qswitch.start()
            self.shutter = True
            self._wait_for_operational_state(
                running=True, timeout_s=timeout_s, poll_s=poll_s
            )
        except Exception:
            try:
                self.disarm(timeout_s=timeout_s, poll_s=poll_s)
            except Exception as rollback_error:
                raise LaserTransitionError(
                    "laser arm failed and rollback could not verify a safe state"
                ) from rollback_error
            raise

    def disarm(self, *, timeout_s: float = 2.0, poll_s: float = 0.1) -> None:
        """Close shutter and stop Q-switch/flashlamp, then verify all are off."""
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
