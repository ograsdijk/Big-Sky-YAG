from dataclasses import dataclass
from enum import IntEnum
import re
from typing import Optional, Protocol, Tuple, Union

from .bit_handling import Bits
from .interlock import (
    FlashlampInterlock1,
    FlashlampInterlock2,
    FlashlampInterlockState,
    QSwitchInterlock,
    QSwitchInterlockState,
)


class Property:
    def __init__(
        self, name: str, command: str, ret_string: Optional[str] = None, read_only=True
    ):
        self._name = name
        self._command = command
        self._read_only = read_only
        self._ret_string = ret_string
        if ret_string is not None:
            regex_found = list(re.finditer("-.*-", ret_string))
            if len(regex_found) > 0:
                self._span: Optional[Tuple[int, int]] = regex_found[0].span()
            else:
                self._span = None
        else:
            self._span = None

    def __get__(self, instance, owner) -> str:
        retval = instance.query(f"{self._command}")
        if self._span is not None:
            retval = retval[self._span[0] : self._span[1]]
        return retval

    def __set__(self, instance, value: Union[str, float, int]) -> str:
        if self._read_only:
            raise ValueError(f"{self._name} is a read-only attribute")
        else:
            retval = instance.write(f"{self._command}{value}")
            return retval


class IntProperty(Property):
    def __init__(self, *args, lower_upper: Optional[Tuple[int, int]] = None, **kwargs):
        super().__init__(*args, **kwargs)
        self._lower_upper = lower_upper

    def __get__(self, instance, owner) -> int: # type: ignore[override]
        val = int(super().__get__(instance, owner))
        return val

    def __set__(self, instance, value: int) -> str: # type: ignore[override]
        assert isinstance(value, int), f"{value} is not of type int"
        if (ul:=self._lower_upper) is not None:
            l,u=ul
            assert (value >= l) & (value <= u), f"value {value} outside of range {l} -> {u}"
        retval = super().__set__(instance, value)
        # check if input value was set properly
        if (span:=self._span) is not None and self._ret_string is not None:
            ret_string = self._ret_string.replace(self._ret_string[span[0]:span[1]], f"{value}")
            assert retval == ret_string
        return retval

class FloatProperty(Property):
    def __init__(self, *args, lower_upper: Optional[Tuple[float, float]] = None,decimals=1, **kwargs):
        super().__init__(*args, **kwargs)
        self._decimals = decimals
        self._lower_upper = lower_upper

    def __get__(self, instance, owner) -> float: # type: ignore[override]
        val = super().__get__(instance, owner)
        return float(val)

    def __set__(self, instance, value: float) -> str: # type: ignore[override]
        assert isinstance(value, float), f"{value} is not of type float"
        if (ul:=self._lower_upper) is not None:
            l,u=ul
            assert (value >= l) & (value <= u), f"value {value} outside of range {l} -> {u}"
        write_multiplier = 10 ** self._decimals
        _value = int(round(value * write_multiplier, 0))
        retval = super().__set__(instance, _value)
        # check if input value was set properly
        if (span:=self._span) is not None and self._ret_string is not None:
            ret_string = self._ret_string.replace(self._ret_string[span[0]:span[1]], f"{round(value,self._decimals)}")
            assert retval == ret_string
        return retval


class BigSkyYag(Protocol):
    def query(self, query: str) -> str:
        ...

    def write(self, command: str) -> str:
        ...


class Trigger(IntEnum):
    INTERNAL = 0
    EXTERNAL = 1


class QSwitchMode(IntEnum):
    AUTO = 0
    BURST = 1
    EXTERNAL = 2


class Status(IntEnum):
    STOP = 0
    SINGLE = 1
    START = 2


@dataclass
class LaserStatus:
    interlock: bool
    flashlamp: Status
    flashlamp_synchronization: Trigger
    simmer: bool
    q_switch: Status
    q_switch_synchronization: Trigger


class Flashlamp:

    voltage = IntProperty(
        name="flashlamp voltage",
        command="V",
        ret_string="voltage  ---- V",
        lower_upper = (500,1800),
        read_only=False,
    )
    voltage_capacitor_sampled = IntProperty(
        name="capacitor voltage sampled", command="VA", ret_string="voltage ac----V"
    )
    voltage_capacitor_instant = IntProperty(
        name="capacitor voltage instant", command="VT", ret_string="voltage it----V"
    )
    energy = FloatProperty(
        name="flashlamp energy",
        command="ENE",
        ret_string="energy    --.-J",
        lower_upper = (7,23),
        decimals=1,
        read_only=False,
    )
    capacitance = FloatProperty(
        name="capacitance",
        command="CAP",
        ret_string="capacity --.-uF",
        lower_upper = (27.,33.),
        decimals=1,
        read_only=False,
    )
    frequency = FloatProperty(
        name="frequency",
        command="F",
        ret_string="freq.  --.-- Hz",
        lower_upper = (1,99.99),
        decimals=2,
        read_only=False,
    )
    counter = IntProperty(
        name="shot counter", command="C", ret_string="ct LP ---------"
    )
    user_counter = IntProperty(
        name="user shot counter", command="UC", ret_string="cu LP ---------"
    )

    def __init__(self, parent: BigSkyYag):
        self.parent = parent
        return

    def query(self, command) -> str:
        return self.parent.query(command)

    def write(self, command) -> str:
        return self.parent.write(command)

    # @property
    # def voltage(self) -> int:
    #     voltage = self.query("V")
    #     voltage = voltage.strip("voltage").strip("V")
    #     return int(voltage)

    # @voltage.setter
    # def voltage(self, voltage: int):
    #     self.write(f"V{voltage}")

    # @property
    # def voltage_capacitor_sampled(self) -> int:
    #     voltage = self.query("VA")
    #     voltage = voltage.strip("voltage ac").strip("V")
    #     return int(voltage)

    # @property
    # def voltage_capacitor_instant(self) -> int:
    #     voltage = self.query("VI")
    #     voltage = voltage.strip("voltage it").strip("V")
    #     return int(voltage)

    # @property
    # def flashlamp_energy(self) -> float:
    #     """
    #     Capacitor energy in μJ

    #     Returns:
    #         float: energy in μJ
    #     """
    #     energy = self.query("ENE")
    #     energy = energy.strip("energy").strip("J")
    #     return float(energy)

    # @flashlamp_energy.setter
    # def flashlamp_energy(self, energy: float):
    #     self.write(f"ENE{int(round(energy*10,0))}")

    # @property
    # def capacitor(self) -> float:
    #     """
    #     Get the capacitance

    #     Returns:
    #         float: capacitance in μF
    #     """
    #     capacitance = self.query("CAP")
    #     capacitance = capacitance.strip("capacity").strip("uF")
    #     return float(capacitance)

    # @capacitor.setter
    # def capacitor(self, capacitance: float):
    #     """
    #     Set the capacitance in uF

    #     Args:
    #         capacitance (float): capactiance in uF, up to 1 decimal place.
    #     """
    #     self.write(f"CAP{int(round(capacitance*10,0))}")

    # @property
    # def frequency(self) -> float:
    #     """
    #     Flashlamp frequency in Hz

    #     Returns:
    #         float: frequency in Hz
    #     """
    #     freq = self.query("F")
    #     freq = freq.strip("freq.").strip("Hz")
    #     return float(freq)

    # @frequency.setter
    # def frequency(self, frequency: float):
    #     """
    #     Set the flashlamp frequency in Hz, up to 2 decimals

    #     Args:
    #         frequency (float): flashlamp frequency in Hz
    #     """
    #     self.write(f"CAP{int(round(frequency*100,0))}")

    @property
    def trigger(self) -> Trigger:
        """
        Flashlamp trigger, either internal or external

        Returns:
            Trigger: enum describing the flashlamp state
        """
        mode = self.query("LPM")
        mode = mode.strip("LP synch :").replace(" ", "")
        return Trigger(int(mode))

    @trigger.setter
    def trigger(self, trigger: str):
        """
        Set the flashlamp trigger, either internal or external

        Args:
            trigger (str): trigger type, 'internal' or 'external'

        Raises:
            ValueError: raise error if `trigger` is not `internal` or `external`
        """
        if trigger == "internal":
            self.write("LPM0")
        elif trigger == "external":
            self.write("LPM1")
        else:
            raise ValueError(
                f"flashlamp trigger should be either internal or external, not {trigger}"
            )

    @property
    def interlock(self) -> FlashlampInterlockState:
        interlock_str = self.query("IF")
        interlock_str = "".join(interlock_str.split(" ")[1:])
        if1 = Bits(int(interlock_str, 2))
        interlock_str = self.query("IF2")
        interlock_str = "".join(interlock_str.split(" ")[1:])
        if2 = Bits(int(interlock_str, 2))
        state = dict((i.name, bool(if1.get_bit(i))) for i in FlashlampInterlock1)
        state.update(dict((i.name, bool(if2.get_bit(i))) for i in FlashlampInterlock2))
        return FlashlampInterlockState(**state)

    # @property
    # def counter(self) -> int:
    #     """
    #     Lamp shout counter

    #     Returns:
    #         int: lamp shots
    #     """
    #     counts = self.query("C")
    #     counts = counts.strip("ct LP").replace(" ", "")
    #     return int(counts)

    # @property
    # def counter_user(self) -> int:
    #     """
    #     User lamp shout counter, can be reset with `user_counter_reset`

    #     Returns:
    #         int: user lamp shots
    #     """
    #     counts = self.query("UC")
    #     counts = counts.strip("cu LP").replace(" ", "")
    #     return int(counts)

    def user_counter_reset(self):
        """
        Reset the user lamp shot counter.
        """
        self.write("UC0")

    def activate(self):
        self.write("A")

    def stop(self):
        self.write("S")

    def simmer(self):
        self.write("M")


class QSwitch:
    frequency_divider = IntProperty(
        name="frequency divider",
        command="QSF",
        ret_string="cycle rate F/--",
        lower_upper = (1,99),
        read_only=False,
    )
    pulses = IntProperty(
        name="burst pulses",
        command="QSP",
        ret_string="burst QS    ---",
        lower_upper = (1,999),
        read_only=False,
    )
    counter = IntProperty(
        name="shot counter", command="CQ", ret_string="ct QS ---------"
    )
    counter_user = IntProperty(
        name="user shot counter", command="UCQ", ret_string="cu QS ---------"
    )
    delay = IntProperty(name="delay", command="W", ret_string="delay    --- uS",
        lower_upper = (100, 999), read_only = False)
    pulses_wait = IntProperty(
        name="flashlamp pulses wait", command="QSW", ret_string="QS wait :  ---"
    )

    def __init__(self, parent):
        self.parent = parent
        return

    def query(self, command) -> str:
        return self.parent.query(command)

    def write(self, command) -> str:
        return self.parent.write(command)

    @property
    def mode(self) -> QSwitchMode:
        mode = self.query("QSM")
        mode = mode.strip("QS MODE :").replace(" ", "")
        return QSwitchMode(int(mode))

    @mode.setter
    def mode(self, mode: str):
        if mode == "auto":
            self.write("QSM0")
        elif mode == "burst":
            self.write("QSM1")
        elif mode == "external":
            self.write("QSM2")
        else:
            raise ValueError(
                f"qswitch mode should be either auto, burst or external, not {mode}"
            )

    # @property
    # def frequency_divider(self) -> int:
    #     divider = self.query("QSF")
    #     divider = divider.strip("cycle rate F/").replace(" ", "")
    #     return int(divider)

    # @frequency_divider.setter
    # def frequency_divider(self, divider: int):
    #     assert (divider > 0) & (divider < 100), "divider outside of range 1 -> 99"
    #     self.write(f"QSF{divider}")

    # @property
    # def pulses(self) -> int:
    #     pulses = self.query("QSP")
    #     pulses.strip("burst QS").replace(" ", "")
    #     return int(pulses)

    # @pulses.setter
    # def pulses(self, pulses: int):
    #     self.write(f"QSP{pulses}")

    # @property
    # def delay(self) -> int:
    #     """
    #     Q-switch delay after flashlamp is fired in us

    #     Returns:
    #         int: Q-switch delay in us
    #     """
    #     delay = self.query("W")
    #     delay.strip("delay").strip("uS").replace(" ", "")
    #     return int(delay)

    # @delay.setter
    # def delay(self, delay: int):
    #     """
    #     Set the Q-switch delay in us

    #     Args:
    #         delay (int): Q-switch delay
    #     """
    #     assert (delay > 100) & (delay < 999), "delay outside of range 100 -> 999 μs"
    #     self.write(f"W{delay}")

    @property
    def status(self) -> bool:
        status = self.query("QOF")
        status = status.strip("QS at run").replace(" ", "")
        return bool(status)

    @property
    def interlock(self) -> QSwitchInterlockState:
        interlock_str = self.query("IQ")
        interlock_str = "".join(interlock_str.split(" ")[1:])
        iq = Bits(int(interlock_str, 2))
        state = dict((i.name, bool(iq.get_bit(i))) for i in QSwitchInterlock)
        return QSwitchInterlockState(**state)

    # @property
    # def pulses_wait(self) -> int:
    #     """
    #     Pulses to wait after starting the flashlamp before enabling the Q-switch

    #     Returns:
    #         int: pulses to wait
    #     """
    #     pulses_wait = self.query("QSW")
    #     pulses_wait.strip("QS wait :").replace(" ", "")
    #     return int(pulses_wait)

    def on(self):
        self.write("QOF1")

    def off(self):
        self.write("QOF0")

    def start(self):
        self.write("PQ")

    def stop(self):
        self.write("SQ")

    def single(self):
        self.write("OQ")
