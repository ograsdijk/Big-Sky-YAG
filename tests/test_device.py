import math
from collections.abc import Iterator

import pytest

from big_sky_yag import (
    BigSkyYag,
    LaserProtocolError,
    LaserTransitionError,
    LaserTransportError,
    Status,
    Trigger,
)
from big_sky_yag.device import SerialInstrument


class FakeInstrument:
    def __init__(self, responses: list[bytes]) -> None:
        self.responses = responses
        self.messages: list[str] = []

    def read(self) -> bytes:
        return self.responses.pop(0)

    def write(self, message: str) -> None:
        self.messages.append(message)


class StateInstrument:
    """Small controller simulator for verified operational transitions."""

    def __init__(
        self,
        *,
        ignore_activate: bool = False,
        ignore_stop: bool = False,
        invalid_shutter_response: bool = False,
    ) -> None:
        self.messages: list[str] = []
        self.flashlamp = Status.STOP
        self.qswitch = Status.STOP
        self.shutter = False
        self.ignore_activate = ignore_activate
        self.ignore_stop = ignore_stop
        self.invalid_shutter_response = invalid_shutter_response
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
            # Keep unresolved labels out of production validation: both the
            # manual's F/S and this historical fake's L/M are structurally valid.
            flashlamp = int(self.flashlamp) + 4
            qswitch = int(self.qswitch) + 4
            self._response = f"I 0 L {flashlamp} M 0 Q {qswitch}\r\n".encode()
        elif command == "R":
            if self.invalid_shutter_response:
                self._response = b"controller error\r\n"
            else:
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


def test_existing_numbered_address_format_is_preserved_pending_verification() -> None:
    instrument = FakeInstrument([b"CG pump       1\r\n"])
    yag = BigSkyYag("COM4", serial_number=42, instrument=instrument)

    response = yag.write("P1")

    assert response == "CG pump       1"
    assert instrument.messages == ["42P1"]


@pytest.mark.parametrize("serial_number", [True, object()])
def test_invalid_serial_number_raises_value_error(serial_number: object) -> None:
    instrument = FakeInstrument([])
    yag = BigSkyYag(
        "COM4",
        instrument=instrument,
        serial_number=serial_number,  # type: ignore[arg-type]
    )

    with pytest.raises(ValueError, match="Serial number is not valid"):
        yag.query("SN")


def test_read_strips_line_endings_and_uses_configured_encoding() -> None:
    instrument = FakeInstrument([b"\r\ncaf\xe9\r\n"])
    yag = BigSkyYag("COM4", instrument=instrument, encoding="latin-1")

    assert yag.read() == "café"


def test_read_rejects_invalid_text() -> None:
    yag = BigSkyYag("COM4", instrument=FakeInstrument([b"\xff\r\n"]), encoding="ascii")

    with pytest.raises(LaserTransportError, match="not valid text"):
        yag.read()


def test_serial_instrument_writes_and_reads_fixed_frame(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeSerial:
        def __init__(self, **kwargs: object) -> None:
            self.kwargs = kwargs
            self.writes: list[bytes] = []
            self.reset_count = 0
            self.closed = False
            serial_instances.append(self)

        def read(self, n: int) -> bytes:
            assert n == 17
            return b"\r\nok             "

        def write(self, message: bytes) -> None:
            self.writes.append(message)

        def reset_input_buffer(self) -> None:
            self.reset_count += 1

        def close(self) -> None:
            self.closed = True

    serial_instances: list[FakeSerial] = []

    monkeypatch.setattr("big_sky_yag.device.serial.Serial", FakeSerial)

    instrument = SerialInstrument("COM4", baud_rate=19200, timeout=1.0)
    instrument.write(">SN")

    assert instrument.read() == b"\r\nok             "
    assert serial_instances[0].kwargs["port"] == "COM4"
    assert serial_instances[0].kwargs["baudrate"] == 19200
    assert serial_instances[0].kwargs["timeout"] == 1.0
    assert serial_instances[0].writes == [b">SN\r\n"]
    assert serial_instances[0].reset_count == 1


def test_serial_instrument_rejects_incomplete_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeSerial:
        def __init__(self, **kwargs: object) -> None:
            pass

        def read(self, n: int) -> bytes:
            return b"partial"

        def write(self, message: bytes) -> None:
            pass

        def reset_input_buffer(self) -> None:
            pass

        def close(self) -> None:
            pass

    monkeypatch.setattr("big_sky_yag.device.serial.Serial", FakeSerial)
    instrument = SerialInstrument("COM4")

    with pytest.raises(LaserTransportError, match="expected 17 bytes, received 7"):
        instrument.read()


def test_context_manager_closes_only_owned_transport(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    closed = False

    class FakeSerial:
        def __init__(self, **kwargs: object) -> None:
            pass

        def read(self, n: int) -> bytes:
            return b"\r\nok             "

        def write(self, message: bytes) -> None:
            pass

        def reset_input_buffer(self) -> None:
            pass

        def close(self) -> None:
            nonlocal closed
            closed = True

    monkeypatch.setattr("big_sky_yag.device.serial.Serial", FakeSerial)

    with BigSkyYag("COM4") as yag:
        assert isinstance(yag, BigSkyYag)

    assert closed is True

    injected = FakeInstrument([])
    with BigSkyYag("unused", instrument=injected):
        pass
    assert not hasattr(injected, "closed")


@pytest.mark.parametrize(
    ("response", "expected"),
    [(b"shutter opened\r\n", True), (b"shutter closed\r\n", False)],
)
def test_shutter_accepts_only_known_states(response: bytes, expected: bool) -> None:
    yag = BigSkyYag("COM4", instrument=FakeInstrument([response]))

    assert yag.shutter is expected


@pytest.mark.parametrize("response", [b"unknown\r\n", b"shutter open\r\n", b"\r\n"])
def test_shutter_rejects_unknown_states(response: bytes) -> None:
    yag = BigSkyYag("COM4", instrument=FakeInstrument([response]))

    with pytest.raises(LaserProtocolError, match="unexpected R response"):
        _ = yag.shutter


@pytest.mark.parametrize(
    ("response", "expected"),
    [(b"CG pump       0\r\n", False), (b"CG pump       1\r\n", True)],
)
def test_pump_accepts_only_binary_controller_states(
    response: bytes, expected: bool
) -> None:
    yag = BigSkyYag("COM4", instrument=FakeInstrument([response]))

    assert yag.pump is expected


@pytest.mark.parametrize(
    "response", [b"pump 1\r\n", b"CG pump 2\r\n", b"CG pump on\r\n"]
)
def test_pump_rejects_malformed_states(response: bytes) -> None:
    yag = BigSkyYag("COM4", instrument=FakeInstrument([response]))

    with pytest.raises(LaserProtocolError, match="unexpected P response"):
        _ = yag.pump


@pytest.mark.parametrize("response", [b"s/number 123\r\n", b"S/Number 123\r\n"])
def test_serial_number_accepts_documented_capitalization_variants(
    response: bytes,
) -> None:
    yag = BigSkyYag("COM4", instrument=FakeInstrument([response]))

    assert yag.serial_number == "123"


@pytest.mark.parametrize("response", [b"serial 123\r\n", b"s/number\r\n"])
def test_serial_number_rejects_unknown_response(response: bytes) -> None:
    yag = BigSkyYag("COM4", instrument=FakeInstrument([response]))

    with pytest.raises(LaserProtocolError, match="unexpected SN response"):
        _ = yag.serial_number


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


@pytest.mark.parametrize("code", [0, 1, 2, 4, 5, 6])
def test_laser_status_accepts_every_documented_subsystem_code(code: int) -> None:
    response = f"I 0 F {code} S 1 Q {code}\r\n".encode()
    yag = BigSkyYag("COM4", instrument=FakeInstrument([response]))

    status = yag.laser_status

    expected_status = Status(code if code < 4 else code - 4)
    expected_trigger = Trigger.INTERNAL if code < 4 else Trigger.EXTERNAL
    assert status.flashlamp is expected_status
    assert status.flashlamp_synchronization is expected_trigger
    assert status.q_switch is expected_status
    assert status.q_switch_synchronization is expected_trigger


@pytest.mark.parametrize(
    "response",
    [
        b"malformed\r\n",
        b"I 0 L bad M 0 Q 6\r\n",
        b"I 0 L 7 M 0 Q 6\r\n",
        b"I -1 L 2 M 0 Q 2\r\n",
        b"I 0 L 2 M 2 Q 2\r\n",
        b"X 0 L 2 M 0 Q 2\r\n",
        b"I 0 long 2 M 0 Q 2\r\n",
    ],
)
def test_laser_status_rejects_malformed_response(response: bytes) -> None:
    yag = BigSkyYag("COM4", instrument=FakeInstrument([response]))

    with pytest.raises(LaserProtocolError, match="unexpected WOR response"):
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


def test_disarm_rejects_malformed_shutter_verification() -> None:
    instrument = StateInstrument(invalid_shutter_response=True)
    yag = BigSkyYag("COM4", instrument=instrument)

    with pytest.raises(LaserTransitionError, match="did not become disarmed") as exc:
        yag.disarm(timeout_s=0)

    assert isinstance(exc.value.__cause__, LaserProtocolError)


def test_disarm_failure_is_reported_when_safe_state_cannot_be_verified() -> None:
    instrument = StateInstrument(ignore_stop=True)
    instrument.flashlamp = Status.START
    instrument.qswitch = Status.START
    instrument.shutter = True
    yag = BigSkyYag("COM4", instrument=instrument)

    with pytest.raises(LaserTransitionError, match="did not become disarmed"):
        yag.disarm(timeout_s=0)


@pytest.mark.parametrize(
    ("keyword", "value"),
    [
        ("timeout_s", -1.0),
        ("timeout_s", math.inf),
        ("timeout_s", math.nan),
        ("poll_s", 0.0),
        ("poll_s", -1.0),
        ("poll_s", math.inf),
    ],
)
def test_transition_timing_is_validated_before_commands(
    keyword: str, value: float
) -> None:
    instrument = StateInstrument()
    yag = BigSkyYag("COM4", instrument=instrument)
    arguments = {keyword: value}

    with pytest.raises(ValueError, match=keyword):
        yag.arm(**arguments)

    assert instrument.messages == []


def test_wait_can_recover_from_a_transient_status_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    instrument = StateInstrument()
    yag = BigSkyYag("COM4", instrument=instrument)
    original_query = yag.query
    failures = iter([True, False])

    def flaky_query(command: str) -> str:
        if command == "WOR" and next(failures, False):
            return "malformed"
        return original_query(command)

    monkeypatch.setattr(yag, "query", flaky_query)
    yag.arm(timeout_s=0.05, poll_s=0.001)

    assert instrument.shutter is True


def _walk_exception_group(
    group: BaseExceptionGroup[BaseException],
) -> Iterator[Exception]:
    for error in group.exceptions:
        if isinstance(error, BaseExceptionGroup):
            yield from _walk_exception_group(error)
        elif isinstance(error, Exception):
            yield error


def test_arm_and_failed_rollback_preserve_both_failures() -> None:
    instrument = StateInstrument(
        ignore_activate=True, ignore_stop=True, invalid_shutter_response=True
    )
    yag = BigSkyYag("COM4", instrument=instrument)

    with pytest.raises(
        LaserTransitionError, match="rollback could not verify"
    ) as captured:
        yag.arm(timeout_s=0)

    cause = captured.value.__cause__
    assert isinstance(cause, ExceptionGroup)
    failures = list(_walk_exception_group(cause))
    assert sum(isinstance(error, LaserTransitionError) for error in failures) >= 2
