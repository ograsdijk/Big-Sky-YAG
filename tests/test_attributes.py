from typing import cast

import pytest

from big_sky_yag import BigSkyYagProtocolError, QSwitchMode, Trigger
from big_sky_yag.attributes import Flashlamp, FloatProperty, IntProperty, QSwitch


class FakeParent:
    def __init__(self, responses: list[str]) -> None:
        self.responses = responses
        self.messages: list[str] = []

    def query(self, command: str) -> str:
        self.messages.append(command)
        return self.responses.pop(0)

    def write(self, command: str) -> str:
        self.messages.append(command)
        return self.responses.pop(0)


def test_descriptor_supports_class_access() -> None:
    assert isinstance(Flashlamp.voltage, IntProperty)


def test_int_and_float_properties_parse_fixed_fields() -> None:
    parent = FakeParent(["voltage  1150 V", "freq.  10.00 Hz"])
    flashlamp = Flashlamp(parent)

    assert flashlamp.voltage == 1150
    assert flashlamp.frequency == 10.0


def test_properties_reject_short_or_non_numeric_fields() -> None:
    parent = FakeParent(["short", "freq.  xx.xx Hz"])
    flashlamp = Flashlamp(parent)

    with pytest.raises(BigSkyYagProtocolError, match="unexpected V response"):
        _ = flashlamp.voltage
    with pytest.raises(BigSkyYagProtocolError, match="unexpected F response"):
        _ = flashlamp.frequency


def test_int_property_validates_type_range_and_echo() -> None:
    parent = FakeParent(["voltage  0900 V", "voltage  0800 V", "bad"])
    prop = IntProperty(
        "flashlamp voltage",
        "V",
        ret_string="voltage  ---- V",
        read_only=False,
        lower_upper=(500, 1800),
    )

    prop.__set__(parent, 900)
    assert parent.messages == ["V900"]

    with pytest.raises(ValueError, match="failed to set"):
        prop.__set__(parent, 900)
    with pytest.raises(BigSkyYagProtocolError, match="write response"):
        prop.__set__(parent, 900)
    with pytest.raises(TypeError, match="not of type int"):
        prop.__set__(parent, True)
    with pytest.raises(ValueError, match="outside of range"):
        prop.__set__(parent, 1801)


def test_float_property_scales_value_and_validates_echo() -> None:
    parent = FakeParent(["freq.  10.00 Hz", "freq.  11.00 Hz", "bad"])
    prop = FloatProperty(
        "frequency",
        "F",
        ret_string="freq.  --.-- Hz",
        read_only=False,
        lower_upper=(1.0, 99.99),
        decimals=2,
    )

    prop.__set__(parent, 10.0)
    assert parent.messages == ["F1000"]

    with pytest.raises(ValueError, match="failed to set"):
        prop.__set__(parent, 10.0)
    with pytest.raises(BigSkyYagProtocolError, match="write response"):
        prop.__set__(parent, 10.0)
    with pytest.raises(TypeError, match="not of type float"):
        prop.__set__(parent, cast(float, 10))
    with pytest.raises(ValueError, match="outside of range"):
        prop.__set__(parent, 100.0)


def test_read_only_property_rejects_assignment() -> None:
    parent = FakeParent([])
    prop = IntProperty("counter", "C")

    with pytest.raises(ValueError, match="read-only"):
        prop.__set__(parent, 1)


@pytest.mark.parametrize(
    ("response", "expected"),
    [("LP synch :  0  ", Trigger.INTERNAL), ("LP synch :  1  ", Trigger.EXTERNAL)],
)
def test_flashlamp_trigger_parses_known_modes(response: str, expected: Trigger) -> None:
    assert Flashlamp(FakeParent([response])).trigger is expected


@pytest.mark.parametrize("response", ["LP synch :  2", "wrong 0", "LP synch : x"])
def test_flashlamp_trigger_rejects_unknown_response(response: str) -> None:
    with pytest.raises(BigSkyYagProtocolError, match="unexpected LPM response"):
        _ = Flashlamp(FakeParent([response])).trigger


@pytest.mark.parametrize(
    ("response", "expected"),
    [
        ("QS mode :   0  ", QSwitchMode.AUTO),
        ("QS mode :   1  ", QSwitchMode.BURST),
        ("QS mode :   2  ", QSwitchMode.EXTERNAL),
    ],
)
def test_qswitch_mode_parses_known_modes(response: str, expected: QSwitchMode) -> None:
    assert QSwitch(FakeParent([response])).mode is expected


@pytest.mark.parametrize(
    ("response", "expected"), [("QS at run     0", False), ("QS at run     1", True)]
)
def test_qswitch_status_accepts_only_binary_state(
    response: str, expected: bool
) -> None:
    assert QSwitch(FakeParent([response])).status is expected


@pytest.mark.parametrize("response", ["QS at run 2", "not a status", "QS at run on"])
def test_qswitch_status_rejects_unknown_response(response: str) -> None:
    with pytest.raises(BigSkyYagProtocolError, match="unexpected QOF response"):
        _ = QSwitch(FakeParent([response])).status


def test_mode_and_operation_setters_emit_documented_commands() -> None:
    parent = FakeParent(["ok"] * 12)
    flashlamp = Flashlamp(parent)
    qswitch = QSwitch(parent)

    flashlamp.trigger = Trigger.EXTERNAL
    flashlamp.activate()
    flashlamp.simmer()
    flashlamp.stop()
    flashlamp.user_counter_reset()
    qswitch.mode = QSwitchMode.BURST
    qswitch.on()
    qswitch.off()
    qswitch.start()
    qswitch.stop()
    qswitch.single()

    assert parent.messages == [
        "LPM1",
        "A",
        "M",
        "S",
        "UC0",
        "QSM1",
        "QOF1",
        "QOF0",
        "PQ",
        "SQ",
        "OQ",
    ]


def test_invalid_mode_setters_raise_before_writing() -> None:
    parent = FakeParent([])

    with pytest.raises(ValueError, match="internal or external"):
        Flashlamp(parent).trigger = cast(Trigger, "invalid")
    with pytest.raises(ValueError, match="auto, burst or external"):
        QSwitch(parent).mode = cast(QSwitchMode, "invalid")
    assert parent.messages == []


def test_new_read_descriptors_parse_captured_templates() -> None:
    # Templates captured from the real controller (2026-08-07, SN 062).
    flashlamp = Flashlamp(FakeParent(["Voltage m0950 V"]))
    assert flashlamp.voltage_average == 950

    flashlamp = Flashlamp(FakeParent(["dis charg 00.0S", "ena charg 00.0S"]))
    assert flashlamp.idle_fire_interval == 0.0
    assert flashlamp.enable_fire_interval == 0.0

    qswitch = QSwitch(
        FakeParent(["dly QS m 100 uS", "dly QS M 500 uS", "QS wait :   000"])
    )
    assert qswitch.delay_min == 100
    assert qswitch.delay_max == 500
    assert qswitch.pulses_wait == 0


def test_new_setters_emit_commands_and_verify_echo() -> None:
    parent = FakeParent(
        [
            "QS wait :   100",
            "dly QS m 150 uS",
            "dly QS M 350 uS",
            "dis charg 01.0S",
            "ena charg 02.5S",
        ]
    )
    qswitch = QSwitch(parent)
    flashlamp = Flashlamp(parent)

    qswitch.pulses_wait = 100
    qswitch.delay_min = 150
    qswitch.delay_max = 350
    flashlamp.idle_fire_interval = 1.0
    flashlamp.enable_fire_interval = 2.5

    assert parent.messages == ["QSW100", "WMN150", "WMX350", "D10", "E25"]


@pytest.mark.parametrize("value", [99, 1000])
def test_factory_delay_limit_setters_reject_out_of_range(value: int) -> None:
    with pytest.raises(ValueError, match="outside of range"):
        QSwitch(FakeParent([])).delay_min = value


def test_counter_maintenance_methods_emit_documented_commands() -> None:
    parent = FakeParent(["ok", "ok"])
    QSwitch(parent).counter_user_reset()
    Flashlamp(parent).save_user_counter()

    assert parent.messages == ["UCQ0", "SUC"]


def test_flashlamp_interlocks_use_second_snapshot_and_decode_known_bits() -> None:
    # Hardware verified (2026-08-07): the stale one-deep sample is labelled
    # `IF1`; the fresh sample used for the state is labelled `IF.`.
    parent = FakeParent(
        [
            "IF1 00 00 00 00",
            "IF. 10 10 00 00",
            "IF2 00 00 00 00",
            "IF2 00 10 01 00",
        ]
    )

    state = Flashlamp(parent).interlock

    assert state.WATER_FLOW is True
    assert state.WATER_LEVEL is True
    assert state.CAPACITOR_LOAD_FAIL is True
    assert state.WATER_TEMP is True
    assert state.LAMP_HEAD_CONN is False
    assert parent.messages == ["IF", "IF", "IF2", "IF2"]


@pytest.mark.parametrize("fresh_prefix", ["IF.", "IF1", "IF"])
def test_flashlamp_interlock_accepts_all_group1_prefixes(fresh_prefix: str) -> None:
    parent = FakeParent(
        [
            "IF1 00 00 00 00",
            f"{fresh_prefix} 00 00 00 00",
            "IF2 00 00 00 00",
            "IF2 00 00 00 00",
        ]
    )

    state = Flashlamp(parent).interlock

    assert state.WATER_FLOW is False


def test_qswitch_interlock_uses_second_snapshot_and_decodes_shutter_closed() -> None:
    parent = FakeParent(["IQS 00 00 00 00", "IQS 00 00 00 10"])

    state = QSwitch(parent).interlock

    assert state.SHUTTER_CLOSED is True
    assert state.EMISSION_INHIBITED is False
    assert parent.messages == ["IQ", "IQ"]


def test_qswitch_interlock_decodes_emission_inhibited() -> None:
    # Captured on hardware (2026-08-07) during the Q-switch inhibit window with
    # the shutter open: `IQS 10 00 00 00` -> emission-inhibited bit (index 0).
    parent = FakeParent(["IQS 00 00 00 00", "IQS 10 00 00 00"])

    state = QSwitch(parent).interlock

    assert state.EMISSION_INHIBITED is True
    assert state.WATER_TEMP is False
    assert state.SHUTTER_CLOSED is False


@pytest.mark.parametrize(
    "response",
    ["bad", "IF1 00 00 00", "IF1 00 00 00 0x", "wrong 00 00 00 00"],
)
def test_interlocks_reject_malformed_current_snapshot(response: str) -> None:
    parent = FakeParent(["IF1 00 00 00 00", response])

    with pytest.raises(BigSkyYagProtocolError, match="unexpected interlock response"):
        _ = Flashlamp(parent).interlock
