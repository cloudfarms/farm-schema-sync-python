from typing import TypedDict
from my_app.enums import State

class SyncItem(TypedDict):
    type: State
    data: tuple
