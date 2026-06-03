from typing import TypedDict
from farmSync.core.enums import State

class SyncItem(TypedDict):
    type: State
    data: tuple
