import pytest

from big_sky_yag.bit_handling import Bits
from big_sky_yag.interlock import FlashlampInterlock1


def test_bits_get_set_and_enum_helpers() -> None:
    bits = Bits(0)

    bits.set_bit(2, True)
    bits.set_value(FlashlampInterlock1.WATER_FLOW, 1)

    assert bits.value == 5
    assert bits.get_bit(2) == 1
    assert bits.get_value(FlashlampInterlock1.WATER_FLOW) == 1
    assert bits.get_set_bits() == [0, 2]

    bits.set_bit(2, False)
    assert bits.value == 1


@pytest.mark.parametrize("value", [-1, -100])
def test_bits_rejects_negative_field(value: int) -> None:
    with pytest.raises(ValueError, match="non-negative"):
        Bits(value)


def test_bits_rejects_negative_index_and_non_boolean_value() -> None:
    bits = Bits(0)

    with pytest.raises(ValueError, match="index"):
        bits.get_bit(-1)
    with pytest.raises(ValueError, match="index"):
        bits.set_bit(-1, True)
    with pytest.raises(ValueError, match="boolean"):
        bits.set_bit(1, 2)
