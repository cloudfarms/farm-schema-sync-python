from typing import TypedDict
from my_app.enums import State, CsvOperation

class SectionItem(TypedDict):
    type: State
    table: str
    operation: CsvOperation
