from dataclasses import dataclass
from enum import IntEnum


@dataclass(frozen=True, slots=True)
class FlashlampInterlockState:
    WATER_FLOW: bool
    WATER_LEVEL: bool
    LAMP_HEAD_CONN: bool
    AUXILIARY_CONN: bool
    EXT_INTERLOCK: bool
    COVER_OPEN: bool
    CAPACITOR_LOAD_FAIL: bool
    SIMMER_FAIL: bool
    WATER_TEMP: bool


class FlashlampInterlock1(IntEnum):
    WATER_FLOW = 0
    WATER_LEVEL = 2
    LAMP_HEAD_CONN = 3
    AUXILIARY_CONN = 4
    EXT_INTERLOCK = 5
    COVER_OPEN = 6


class FlashlampInterlock2(IntEnum):
    CAPACITOR_LOAD_FAIL = 2
    SIMMER_FAIL = 3
    WATER_TEMP = 5


@dataclass(frozen=True, slots=True)
class QSwitchInterlockState:
    EMISSION_INHIBITED: bool
    WATER_TEMP: bool
    SHUTTER_CLOSED: bool


class QSwitchInterlock(IntEnum):
    # Bit indices (after the printed a..h field is reversed) confirmed on the
    # real controller 2026-08-07: `IQS 10 00 00 00` during the Q-switch inhibit
    # window sets bit 0 (emission inhibited), and `IQS 00 00 00 10` with the
    # shutter closed sets bit 6. Water temperature (bit 1) follows the same
    # reversed manual order but was not asserted (needs a thermal fault).
    EMISSION_INHIBITED = 0
    WATER_TEMP = 1
    SHUTTER_CLOSED = 6
