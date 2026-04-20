from pydantic import BaseModel
from models import RsColumnInfo

class TableInfo(BaseModel):
    name: str
    columns: list[RsColumnInfo]
    key: list[str]