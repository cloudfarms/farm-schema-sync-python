from typing import TypedDict
from farmSync.core.enums import State, CsvOperation

class SectionItem(TypedDict):
    type: State
    table: str
    operation: CsvOperation
