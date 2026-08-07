import re
from dataclasses import dataclass
from enum import IntEnum
from typing import Any, Generic, Protocol, TypeVar, cast, overload

from .bit_handling import Bits
from .errors import BigSkyYagProtocolError
from .interlock import (
    FlashlampInterlock1,
    FlashlampInterlock2,
    FlashlampInterlockState,
    QSwitchInterlock,
    QSwitchInterlockState,
)


class CommandController(Protocol):
    def query(self, query: str) -> str: ...

    def write(self, command: str) -> str: ...


ValueT = TypeVar("ValueT")


class Property(Generic[ValueT]):
    def __init__(
        self,
        name: str,
        command: str,
        ret_string: str | None = None,
        read_only: bool = True,
    ) -> None:
        self._name = name
        self._command = command
        self._read_only = read_only
        self._ret_string = ret_string
        if ret_string is not None:
            regex_found = list(re.finditer("-.*-", ret_string))
            if len(regex_found) > 0:
                self._span: tuple[int, int] | None = regex_found[0].span()
            else:
                self._span = None
        else:
            self._span = None

    @overload
    def __get__(self, instance: None, owner: type[Any]) -> "Property[ValueT]": ...

    @overload
    def __get__(
        self, instance: CommandController, owner: type[Any] | None = None
    ) -> ValueT: ...

    def __get__(
        self, instance: CommandController | None, owner: type[Any] | None = None
    ) -> "Property[ValueT] | ValueT":
        if instance is None:
            return self
        retval = instance.query(self._command)
        return self._parse_response(retval)

    def _extract_field(self, response: str) -> str:
        if self._span is not None:
            start, end = self._span
            if len(response) < end:
                raise BigSkyYagProtocolError(
                    f"unexpected {self._command} response for {self._name}: "
                    f"{response!r}"
                )
            return response[start:end]
        return response

    def _parse_response(self, response: str) -> ValueT:
        return cast(ValueT, self._extract_field(response))

    def __set__(self, instance: CommandController, value: ValueT) -> None:
        self._write_value(instance, value)

    def _write_value(self, instance: CommandController, value: object) -> str:
        if self._read_only:
            raise ValueError(f"{self._name} is a read-only attribute")
        return instance.write(f"{self._command}{value}")


class IntProperty(Property[int]):
    def __init__(
        self,
        name: str,
        command: str,
        ret_string: str | None = None,
        read_only: bool = True,
        lower_upper: tuple[int, int] | None = None,
    ) -> None:
        super().__init__(name, command, ret_string, read_only)
        self._lower_upper = lower_upper

    def _parse_response(self, response: str) -> int:
        try:
            return int(self._extract_field(response))
        except ValueError as exc:
            raise BigSkyYagProtocolError(
                f"unexpected {self._command} response for {self._name}: {response!r}"
            ) from exc

    def __set__(self, instance: CommandController, value: int) -> None:
        if not isinstance(value, int) or isinstance(value, bool):
            raise TypeError(f"{value} is not of type int")
        if (ul := self._lower_upper) is not None:
            lower, upper = ul
            if not lower <= value <= upper:
                raise ValueError(f"value {value} outside of range {lower} -> {upper}")
        retval = self._write_value(instance, value)
        if (span := self._span) is not None and self._ret_string is not None:
            try:
                echoed = int(retval[span[0] : span[1]])
            except (TypeError, ValueError) as exc:
                raise BigSkyYagProtocolError(
                    f"unexpected {self._command} write response for {self._name}: "
                    f"{retval!r}"
                ) from exc
            if echoed != value:
                raise ValueError(f"failed to set {self._name} to {value}")


class FloatProperty(Property[float]):
    def __init__(
        self,
        name: str,
        command: str,
        ret_string: str | None = None,
        read_only: bool = True,
        lower_upper: tuple[float, float] | None = None,
        decimals: int = 1,
    ) -> None:
        super().__init__(name, command, ret_string, read_only)
        self._decimals = decimals
        self._lower_upper = lower_upper

    def _parse_response(self, response: str) -> float:
        try:
            return float(self._extract_field(response))
        except ValueError as exc:
            raise BigSkyYagProtocolError(
                f"unexpected {self._command} response for {self._name}: {response!r}"
            ) from exc

    def __set__(self, instance: CommandController, value: float) -> None:
        if not isinstance(value, float):
            raise TypeError(f"{value} is not of type float")
        if (ul := self._lower_upper) is not None:
            lower, upper = ul
            if not lower <= value <= upper:
                raise ValueError(f"value {value} outside of range {lower} -> {upper}")
        write_multiplier = 10**self._decimals
        _value = int(round(value * write_multiplier, 0))
        retval = self._write_value(instance, _value)
        if (span := self._span) is not None and self._ret_string is not None:
            # Compare the echoed value numerically; the device formats with a
            # fixed number of decimals (e.g. "28.00"), so a string rebuild would
            # spuriously fail on trailing zeros.
            try:
                echoed = float(retval[span[0] : span[1]])
            except (TypeError, ValueError) as exc:
                raise BigSkyYagProtocolError(
                    f"unexpected {self._command} write response for {self._name}: "
                    f"{retval!r}"
                ) from exc
            if round(echoed, self._decimals) != round(value, self._decimals):
                raise ValueError(f"failed to set {self._name} to {value}")


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


@dataclass(frozen=True, slots=True)
class LaserStatus:
    interlock: bool
    flashlamp: Status
    flashlamp_synchronization: Trigger
    simmer: bool
    q_switch: Status
    q_switch_synchronization: Trigger

    @property
    def flashlamp_running(self) -> bool:
        """Whether the controller reports continuous flashlamp operation."""
        return self.flashlamp is Status.START

    @property
    def qswitch_running(self) -> bool:
        """Whether the controller reports continuous Q-switch operation."""
        return self.q_switch is Status.START

    @property
    def qswitch(self) -> Status:
        """Alias for :attr:`q_switch`, matching the `yag.qswitch` device name."""
        return self.q_switch

    @property
    def qswitch_synchronization(self) -> Trigger:
        """Alias for :attr:`q_switch_synchronization`."""
        return self.q_switch_synchronization


class Flashlamp:
    voltage = IntProperty(
        name="flashlamp voltage",
        command="V",
        ret_string="voltage  ---- V",
        lower_upper=(500, 1800),
        read_only=False,
    )
    voltage_capacitor_sampled = IntProperty(
        name="capacitor voltage sampled", command="VA", ret_string="voltage ac----V"
    )
    voltage_capacitor_instant = IntProperty(
        name="capacitor voltage instant", command="VI", ret_string="voltage it----V"
    )
    energy = FloatProperty(
        name="flashlamp energy",
        command="ENE",
        ret_string="energy    --.-J",
        lower_upper=(7, 23),
        decimals=1,
        read_only=False,
    )
    capacitance = FloatProperty(
        name="capacitance",
        command="CAP",
        ret_string="capacity --.-uF",
        lower_upper=(27.0, 33.0),
        decimals=1,
        read_only=False,
    )
    frequency = FloatProperty(
        name="frequency",
        command="F",
        ret_string="freq.  --.-- Hz",
        lower_upper=(1, 99.99),
        decimals=2,
        read_only=False,
    )
    voltage_average = IntProperty(
        name="average lamp voltage", command="VMO", ret_string="Voltage m---- V"
    )
    counter = IntProperty(
        name="shot counter", command="C", ret_string="ct LP ---------"
    )
    user_counter = IntProperty(
        name="user shot counter", command="UC", ret_string="cu LP ---------"
    )
    idle_fire_interval = FloatProperty(
        name="idle-fire interval in s",
        command="D",
        ret_string="dis charg --.-S",
        lower_upper=(0.0, 99.9),
        decimals=1,
        read_only=False,
    )
    enable_fire_interval = FloatProperty(
        name="enable-fire interval in s",
        command="E",
        ret_string="ena charg --.-S",
        lower_upper=(0.0, 99.9),
        decimals=1,
        read_only=False,
    )

    def __init__(self, parent: CommandController) -> None:
        self.parent = parent

    def query(self, command: str) -> str:
        return self.parent.query(command)

    def write(self, command: str) -> str:
        return self.parent.write(command)

    @staticmethod
    def _parse_mode(response: str, prefix: str, allowed: set[int], command: str) -> int:
        if not response.startswith(prefix):
            raise BigSkyYagProtocolError(f"unexpected {command} response: {response!r}")
        field = response.removeprefix(prefix).strip()
        try:
            value = int(field)
        except ValueError as exc:
            raise BigSkyYagProtocolError(
                f"unexpected {command} response: {response!r}"
            ) from exc
        if value not in allowed:
            raise BigSkyYagProtocolError(f"unexpected {command} response: {response!r}")
        return value

    @property
    def trigger(self) -> Trigger:
        """
        Flashlamp trigger, either internal or external

        Returns:
            Trigger: enum describing the flashlamp state
        """
        mode = self.query("LPM")
        return Trigger(self._parse_mode(mode, "LP synch :", {0, 1}, "LPM"))

    @trigger.setter
    def trigger(self, trigger: Trigger) -> None:
        """
        Set the flashlamp trigger, either internal or external

        Args:
            trigger (Trigger): internal or external trigger mode

        Raises:
            ValueError: raised for an unsupported trigger mode
        """
        legacy_trigger = cast(object, trigger)
        if trigger is Trigger.INTERNAL or legacy_trigger == "internal":
            self.write("LPM0")
        elif trigger is Trigger.EXTERNAL or legacy_trigger == "external":
            self.write("LPM1")
        else:
            raise ValueError(
                "flashlamp trigger should be either internal or external, not"
                f" {trigger}"
            )

    @property
    def interlock(self) -> FlashlampInterlockState:
        # The IF/IF2 registers use a snapshot-on-read (one-deep) buffer: each
        # read returns the value captured at the previous read, then samples
        # fresh. Read twice and use the second to get the current state; the
        # delay between reads is irrelevant. (The WOR/laser_status interlock bit
        # is live and unaffected.)
        self.query("IF")
        # On the tested controller the fresh flashlamp interlock-1 read is
        # labelled `IF.` (the stale one-deep sample is labelled `IF1`); the
        # manual's all-OK form is `IF`. Accept all three.
        interlock_str = _parse_interlock_bits(self.query("IF"), {"IF", "IF1", "IF."})
        if1 = Bits(int(interlock_str, 2))
        self.query("IF2")
        interlock_str = _parse_interlock_bits(self.query("IF2"), {"IF2"})
        if2 = Bits(int(interlock_str, 2))
        state = dict((i.name, bool(if1.get_bit(i))) for i in FlashlampInterlock1)
        state.update(dict((i.name, bool(if2.get_bit(i))) for i in FlashlampInterlock2))
        return FlashlampInterlockState(**state)

    def user_counter_reset(self) -> None:
        """
        Reset the user lamp shot counter.
        """
        self.write("UC0")

    def save_user_counter(self) -> None:
        """Save the current user counter to non-volatile memory (`SUC`)."""
        self.write("SUC")

    def activate(self) -> None:
        self.write("A")

    def stop(self) -> None:
        self.write("S")

    def simmer(self) -> None:
        self.write("M")


class QSwitch:
    frequency_divider = IntProperty(
        name="frequency divider",
        command="QSF",
        ret_string="cycle rate F/--",
        lower_upper=(1, 99),
        read_only=False,
    )
    pulses = IntProperty(
        name="burst pulses",
        command="QSP",
        ret_string="burst QS    ---",
        lower_upper=(1, 999),
        read_only=False,
    )
    counter = IntProperty(
        name="shot counter", command="CQ", ret_string="ct QS ---------"
    )
    user_counter = IntProperty(
        name="user shot counter", command="UCQ", ret_string="cu QS ---------"
    )
    delay = IntProperty(
        name="delay",
        command="W",
        ret_string="delay    --- uS",
        lower_upper=(100, 999),
        read_only=False,
    )
    delay_min = IntProperty(
        name="lower Q-switch delay limit",
        command="WMN",
        ret_string="dly QS m --- uS",
        lower_upper=(100, 999),
        read_only=False,
    )
    delay_max = IntProperty(
        name="upper Q-switch delay limit",
        command="WMX",
        ret_string="dly QS M --- uS",
        lower_upper=(100, 999),
        read_only=False,
    )
    pulses_wait = IntProperty(
        name="flashlamp pulses wait",
        command="QSW",
        ret_string="QS wait :   ---",
        lower_upper=(0, 999),
        read_only=False,
    )

    def __init__(self, parent: CommandController) -> None:
        self.parent = parent

    def query(self, command: str) -> str:
        return self.parent.query(command)

    def write(self, command: str) -> str:
        return self.parent.write(command)

    @property
    def mode(self) -> QSwitchMode:
        mode = self.query("QSM")
        return QSwitchMode(Flashlamp._parse_mode(mode, "QS mode :", {0, 1, 2}, "QSM"))

    @mode.setter
    def mode(self, mode: QSwitchMode) -> None:
        legacy_mode = cast(object, mode)
        if mode is QSwitchMode.AUTO or legacy_mode == "auto":
            self.write("QSM0")
        elif mode is QSwitchMode.BURST or legacy_mode == "burst":
            self.write("QSM1")
        elif mode is QSwitchMode.EXTERNAL or legacy_mode == "external":
            self.write("QSM2")
        else:
            raise ValueError(
                f"qswitch mode should be either auto, burst or external, not {mode}"
            )

    @property
    def status(self) -> bool:
        status = self.query("QOF")
        return bool(Flashlamp._parse_mode(status, "QS at run", {0, 1}, "QOF"))

    @property
    def interlock(self) -> QSwitchInterlockState:
        # IQ uses a snapshot-on-read (one-deep) buffer: each read returns the
        # previous sample, so read twice and use the second for current state.
        self.query("IQ")
        interlock_str = _parse_interlock_bits(self.query("IQ"), {"IQ", "IQS"})
        iq = Bits(int(interlock_str, 2))
        state = dict((i.name, bool(iq.get_bit(i))) for i in QSwitchInterlock)
        return QSwitchInterlockState(**state)

    def user_counter_reset(self) -> None:
        """Reset the Q-switch user shot counter (`UCQ0`)."""
        self.write("UCQ0")

    def on(self) -> None:
        self.write("QOF1")

    def off(self) -> None:
        self.write("QOF0")

    def start(self) -> None:
        self.write("PQ")

    def stop(self) -> None:
        self.write("SQ")

    def single(self) -> None:
        self.write("OQ")


def _parse_interlock_bits(response: str, allowed_prefixes: set[str]) -> str:
    parts = response.split()
    if (
        len(parts) != 5
        or parts[0] not in allowed_prefixes
        or any(len(group) != 2 or set(group) - {"0", "1"} for group in parts[1:])
    ):
        raise BigSkyYagProtocolError(f"unexpected interlock response: {response!r}")
    return "".join(parts[1:])[::-1]
