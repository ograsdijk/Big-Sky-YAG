from enum import IntEnum


class Bits:
    def __init__(self, value: int) -> None:
        if value < 0:
            raise ValueError("bit-field value must be non-negative")
        self.value = value

    def get_set_bits(self) -> list[int]:
        return [i for i in range(self.value.bit_length()) if (self.value >> i & 1)]

    @staticmethod
    def _validate_bit(bit: int) -> None:
        if bit < 0:
            raise ValueError("bit index must be non-negative")

    def set_bit(self, bit: int, bit_value: bool | int) -> None:
        self._validate_bit(bit)
        if bit_value not in (False, True, 0, 1):
            raise ValueError("bit value must be boolean or 0/1")
        value = self.value
        value = value | (1 << bit) if bit_value else value & ~(1 << bit)
        self.value = value

    def get_bit(self, bit: int) -> int:
        self._validate_bit(bit)
        return self.value >> bit & 1

    def set_value(self, enum: IntEnum, val: bool | int) -> None:
        self.set_bit(enum.value, val)

    def get_value(self, enum: IntEnum) -> int:
        return self.get_bit(enum.value)
