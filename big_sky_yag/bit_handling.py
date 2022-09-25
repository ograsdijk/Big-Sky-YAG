from enum import Enum
from typing import List


class Bits:
    def __init__(self, value: int):
        self.value = value

    def get_set_bits(self) -> List:
        return [i for i in range(self.value.bit_length()) if (self.value >> i & 1)]

    def set_bit(self, bit: int, bit_value: int) -> None:
        value = self.value if self.value else 0
        value = value | (1 << bit) if bit_value else value & ~(1 << bit)
        self.value = value

    def get_bit(self, bit: int) -> int:
        return self.value >> bit & 1

    def set_value(self, enum: Enum, val: int) -> None:
        self.set_bit(enum.value, val)

    def get_value(self, enum: Enum) -> int:
        return self.get_bit(enum.value)
