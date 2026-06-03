from pydantic import BaseModel
from farmSync.models import RsColumnInfo

class TableInfo(BaseModel):
    name: str
    columns: list[RsColumnInfo]
    key: list[str]