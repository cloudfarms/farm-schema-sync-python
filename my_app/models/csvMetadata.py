from pydantic import BaseModel
class CsvMetadata(BaseModel):
    requested_since: str | None
    next_since: str | None
