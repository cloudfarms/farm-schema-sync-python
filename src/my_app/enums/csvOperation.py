from enum import Enum

class CsvOperation(str, Enum):
    UPSERT = "upsert"
    DELETE = "delete"