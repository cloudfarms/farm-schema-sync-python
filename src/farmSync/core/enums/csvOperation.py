from enum import Enum

class CsvOperation(str,Enum):
    UPSERT = "upserted"
    DELETE = "deleted"