from typing import List

import pytest

from big_sky_yag import BigSkyYag
from big_sky_yag.attributes import FloatProperty, IntProperty
from big_sky_yag.device import SerialInstrument


class FakeInstrument:
    def __init__(self, responses: List[bytes]):
        self.responses = responses
        self.messages: List[str] = []

    def read(self) -> bytes:
        return self.responses.pop(0)

    def write(self, message: str) -> None:
        self.messages.append(message)


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

        def readline(self) -> bytes:
            return b"ok\r\n"

        def write(self, message: bytes) -> None:
            self.writes.append(message)

        def close(self) -> None:
            pass

    monkeypatch.setattr("big_sky_yag.device.serial.Serial", FakeSerial)

    instrument = SerialInstrument("COM4", baud_rate=19200, timeout=1.0)
    instrument.write(">SN")

    assert instrument.read() == b"ok\r\n"
    assert serial_instances[0].kwargs["port"] == "COM4"
    assert serial_instances[0].kwargs["baudrate"] == 19200
    assert serial_instances[0].kwargs["timeout"] == 1.0
    assert serial_instances[0].writes == [b">SN"]


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
