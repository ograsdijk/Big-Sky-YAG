from dataclasses import dataclass
from enum import IntEnum


@dataclass
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


@dataclass
class QSwitchInterlockState:
    EMISSION_INHIBITED: bool
    WATER_TEMP: bool
    SHUTTER_CLOSED: bool


class QSwitchInterlock(IntEnum):
    EMISSION_INHIBITED = 1
    WATER_TEMP = 2
    SHUTTER_CLOSED = 6
