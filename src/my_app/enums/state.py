from enum import Enum

class State(Enum):
    METADATA_HEADER = 1
    METADATA_ROW = 2
    SECTION_NAME = 3
    HEADER = 4
    ROWS = 5
    WAIT = 6
    START = 7