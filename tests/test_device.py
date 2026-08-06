from typing import List

import pytest

from big_sky_yag import BigSkyYag, LaserTransitionError
from big_sky_yag.attributes import FloatProperty, IntProperty, Status, Trigger
from big_sky_yag.device import SerialInstrument


class FakeInstrument:
    def __init__(self, responses: List[bytes]):
        self.responses = responses
        self.messages: List[str] = []

    def read(self) -> bytes:
        return self.responses.pop(0)

    def write(self, message: str) -> None:
        self.messages.append(message)


class StateInstrument:
    """Small controller simulator for verified operational transitions."""

    def __init__(self, *, ignore_activate: bool = False, ignore_stop: bool = False):
        self.messages: List[str] = []
        self.flashlamp = Status.STOP
        self.qswitch = Status.STOP
        self.shutter = False
        self.ignore_activate = ignore_activate
        self.ignore_stop = ignore_stop
        self._response = b"ok\r\n"

    def read(self) -> bytes:
        return self._response

    def write(self, message: str) -> None:
        self.messages.append(message)
        command = message.removeprefix(">")
        if command == "A" and not self.ignore_activate:
            self.flashlamp = Status.START
        elif command == "S" and not self.ignore_stop:
            self.flashlamp = Status.STOP
        elif command == "PQ":
            self.qswitch = Status.START
        elif command == "SQ" and not self.ignore_stop:
            self.qswitch = Status.STOP
        elif command == "R1":
            self.shutter = True
        elif command == "R0" and not self.ignore_stop:
            self.shutter = False

        if command == "WOR":
            # External synchronization adds four to each subsystem state.
            flashlamp = int(self.flashlamp) + 4
            qswitch = int(self.qswitch) + 4
            self._response = f"I 0 L {flashlamp} M 0 Q {qswitch}\r\n".encode()
        elif command == "R":
            state = "opened" if self.shutter else "closed"
            self._response = f"shutter {state}\r\n".encode()
        else:
            self._response = b"ok\r\n"


def test_query_prefixes_command_without_serial_number() -> None:
    instrument = FakeInstrument([b"s/number 123\r\n"])
    yag = BigSkyYag("COM4", instrument=instrument)

    response = yag.query("SN")

    assert response == "s/number 123"
    assert instrument.messages == [">SN"]


def test_write_prefixes_command_with_serial_number() -> None:
    instrument = FakeInstrument([b"pump 1\r\n"])
    yag = BigSkyYag("COM4", serial_number=42, instrument=instrument)

    response = yag.write("P1")

    assert response == "pump 1"
    assert instrument.messages == ["42P1"]


def test_read_strips_line_endings() -> None:
    instrument = FakeInstrument([b"long response longer than seventeen bytes\r\n"])
    yag = BigSkyYag("COM4", instrument=instrument)

    assert yag.read() == "long response longer than seventeen bytes"


def test_invalid_serial_number_raises_value_error() -> None:
    instrument = FakeInstrument([])
    yag = BigSkyYag("COM4", serial_number=object(), instrument=instrument)  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="Serial number is not valid"):
        yag.query("SN")


def test_serial_instrument_writes_encoded_bytes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serial_instances = []

    class FakeSerial:
        def __init__(self, **kwargs: object) -> None:
            self.kwargs = kwargs
            self.writes: List[bytes] = []
            serial_instances.append(self)

        def read(self, n: int) -> bytes:
            return b"\r\nok             "

        def write(self, message: bytes) -> None:
            self.writes.append(message)

        def reset_input_buffer(self) -> None:
            pass

        def close(self) -> None:
            pass

    monkeypatch.setattr("big_sky_yag.device.serial.Serial", FakeSerial)

    instrument = SerialInstrument("COM4", baud_rate=19200, timeout=1.0)
    instrument.write(">SN")

    assert instrument.read() == b"\r\nok             "
    assert serial_instances[0].kwargs["port"] == "COM4"
    assert serial_instances[0].kwargs["baudrate"] == 19200
    assert serial_instances[0].kwargs["timeout"] == 1.0
    assert serial_instances[0].writes == [b">SN\r\n"]


def test_int_property_validates_type_and_range() -> None:
    prop = IntProperty("value", "V", read_only=False, lower_upper=(1, 10))

    with pytest.raises(TypeError, match="not of type int"):
        prop.__set__(object(), 1.5)  # type: ignore[arg-type]

    with pytest.raises(TypeError, match="not of type int"):
        prop.__set__(object(), True)

    with pytest.raises(ValueError, match="outside of range"):
        prop.__set__(object(), 11)


def test_float_property_validates_type_and_range() -> None:
    prop = FloatProperty("value", "V", read_only=False, lower_upper=(1.0, 10.0))

    with pytest.raises(TypeError, match="not of type float"):
        prop.__set__(object(), 1)

    with pytest.raises(ValueError, match="outside of range"):
        prop.__set__(object(), 11.0)


def test_laser_status_decodes_external_running_state() -> None:
    instrument = StateInstrument()
    instrument.flashlamp = Status.START
    instrument.qswitch = Status.START
    yag = BigSkyYag("COM4", instrument=instrument)

    status = yag.laser_status

    assert status.flashlamp is Status.START
    assert status.flashlamp_running is True
    assert status.flashlamp_synchronization is Trigger.EXTERNAL
    assert status.q_switch is Status.START
    assert status.qswitch_running is True
    assert status.q_switch_synchronization is Trigger.EXTERNAL


@pytest.mark.parametrize(
    "response",
    [b"malformed\r\n", b"I 0 L bad M 0 Q 6\r\n", b"I 0 L 7 M 0 Q 6\r\n"],
)
def test_laser_status_rejects_malformed_response(response: bytes) -> None:
    yag = BigSkyYag("COM4", instrument=FakeInstrument([response]))

    with pytest.raises(ValueError, match="unexpected laser status response"):
        _ = yag.laser_status


def test_arm_starts_and_verifies_complete_operational_state() -> None:
    instrument = StateInstrument()
    yag = BigSkyYag("COM4", instrument=instrument)

    yag.arm(timeout_s=0)

    assert instrument.flashlamp is Status.START
    assert instrument.qswitch is Status.START
    assert instrument.shutter is True
    assert instrument.messages == [">A", ">PQ", ">R1", ">WOR", ">R"]


def test_disarm_stops_and_verifies_complete_safe_state() -> None:
    instrument = StateInstrument()
    instrument.flashlamp = Status.START
    instrument.qswitch = Status.START
    instrument.shutter = True
    yag = BigSkyYag("COM4", instrument=instrument)

    yag.disarm(timeout_s=0)

    assert instrument.flashlamp is Status.STOP
    assert instrument.qswitch is Status.STOP
    assert instrument.shutter is False
    assert instrument.messages == [">R0", ">SQ", ">S", ">WOR", ">R"]


def test_arm_failure_rolls_back_to_verified_safe_state() -> None:
    instrument = StateInstrument(ignore_activate=True)
    yag = BigSkyYag("COM4", instrument=instrument)

    with pytest.raises(LaserTransitionError, match="did not become armed"):
        yag.arm(timeout_s=0)

    assert instrument.flashlamp is Status.STOP
    assert instrument.qswitch is Status.STOP
    assert instrument.shutter is False


def test_disarm_failure_is_reported_when_safe_state_cannot_be_verified() -> None:
    instrument = StateInstrument(ignore_stop=True)
    instrument.flashlamp = Status.START
    instrument.qswitch = Status.START
    instrument.shutter = True
    yag = BigSkyYag("COM4", instrument=instrument)

    with pytest.raises(LaserTransitionError, match="did not become disarmed"):
        yag.disarm(timeout_s=0)
