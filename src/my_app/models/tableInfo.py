from pydantic import BaseModel
from my_app.models import RsColumnInfo

class TableInfo(BaseModel):
    name: str
    columns: list[RsColumnInfo]
    key: list[str]