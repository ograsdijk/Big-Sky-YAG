from typing import Any, List, Optional, Protocol, cast

import serial

from .attributes import Flashlamp, FloatProperty, LaserStatus, QSwitch, Status, Trigger

__all__ = ["BigSkyYag", "SerialInstrument"]


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
        return cast(bytes, self._serial.readline())

    def write(self, message: str) -> None:
        self._serial.write(message.encode(self._encoding))

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
        shutter = shutter.strip("shutter ")
        return True if shutter == "open" else False

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
        pump = pump.strip("CG pump")
        return bool(int(pump))

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
        status_ints = [int(v) for v in status_string.split(" ")[1::2]]
        args: List[Any] = []

        args.append(True if status_ints[0] == 0 else False)

        args.append(Status(status_ints[1] % 4))
        args.append(Trigger.INTERNAL if status_ints[1] <= 3 else Trigger.EXTERNAL)

        args.append(True if status_ints[2] else False)

        args.append(Status(status_ints[3] % 4))
        args.append(Trigger.INTERNAL if status_ints[3] <= 3 else Trigger.EXTERNAL)

        return LaserStatus(*args)
