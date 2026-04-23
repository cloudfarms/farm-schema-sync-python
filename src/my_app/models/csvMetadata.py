from pydantic import BaseModel
from typing import Optional

class CsvMetadata(BaseModel):
    requestedSince: Optional[str] = None
    nextSince: Optional[str] = None
