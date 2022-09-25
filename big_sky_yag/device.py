from typing import Optional
import pyvisa

from .attributes import (
    Flashlamp,
    LaserStatus,
    QSwitch,
    Status,
    Trigger,
    FloatProperty,
)

__all__ = ["BigSkyYag"]


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
    ):
        self.instrument = pyvisa.ResourceManager().open_resource(
            resource_name=resource_name, baud_rate=baud_rate
        )
        self._serial_number = serial_number
        self.flashlamp = Flashlamp(self)
        self.qswitch = QSwitch(self)

    def query(self, query: str) -> str:
        if self._serial_number is None:
            _query = f">{query}"
        elif isinstance(self._serial_number, int):
            _query = f"{self._serial_number}{query}"
        else:
            raise ValueError(f"Serial number is not valid, {self._serial_number}")
        return self.instrument.query(_query)

    def write(self, command: str) -> str:
        if self._serial_number is None:
            _command = f">{command}"
        elif isinstance(self._serial_number, int):
            _command = f"{self._serial_number}{command}"
        else:
            raise ValueError(f"Serial number is not valid, {self._serial_number}")
        return self.instrument.write(_command)

    def save(self):
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
        return self.query("SN")

    # @property
    # def temperature_cooling_group(self) -> float:
    #     """
    #     Get the cooling group temperature in C

    #     Returns:
    #         float: temperature in C
    #     """
    #     temperature = self.query("CG").strip(" ")
    #     temperature = temperature.strip("temp. CG").strip("d")
    #     return float(temperature)

    @property
    def shutter(self) -> bool:
        """
        Device shutter state, True if open False if closed

        Returns:
            bool: shutter state
        """
        shutter = self.query("S")
        shutter = shutter.strip("shutter ")
        return True if shutter == "open" else False

    @shutter.setter
    def shutter(self, state: str):
        """
        Open or close the shutter, with `open` or `close`

        Args:
            state (str): `close` or `open` the shutter

        Raises:
            ValueError: raise error if state is not `open` or `close`
        """
        if state == "open":
            self.write("R1")
        elif state == "close":
            self.write("R0")
        else:
            raise ValueError("state either `open` or `close`")

    @property
    def pump(self) -> bool:
        """
        Get the pump state.

        Returns:
            bool: True if on, False if off
        """
        pump = self.query("P")
        pump.strip("CG pump")
        return bool(pump)

    @pump.setter
    def pump(self, state: str):
        """
        Set the pump state, either `on` or `off`

        Args:
            state (str): `on` or `off`

        Raises:
            ValueError: raise error if state is not `on` or `off`
        """
        if state == "on":
            self.write("P1")
        elif state == "off":
            self.write("P0")
        else:
            raise ValueError("state either on or off")

    @property
    def laser_status(self) -> LaserStatus:
        status_string = self.query("WOR")
        status_ints = [int(v) for v in status_string.split(" ")[1::2]]
        args = []

        # interlock
        args.append(True if status_ints[0] == 0 else False)

        # flashlamp
        args.append(Status(status_ints[1] % 4))
        args.append(Trigger.INTERNAL if status_ints[2] <= 3 else Trigger.EXTERNAL)

        # simmter
        args.append(True if status_ints[3] else False)

        # q-switch
        args.append(Status(status_ints[4] % 4))
        args.append(Trigger.INTERNAL if status_ints[5] <= 3 else Trigger.EXTERNAL)

        return LaserStatus(*args)
