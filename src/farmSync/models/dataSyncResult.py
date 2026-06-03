from typing import TypedDict

class DataSyncResult(TypedDict):
    rowsUpserted: int
    rowsDeleted: int
