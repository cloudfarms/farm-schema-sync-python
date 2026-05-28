from pydantic import BaseModel
from farmSync.models import PythonColumnInfo

class PythonTableInfo(BaseModel):
    name: str
    columns: dict[str, PythonColumnInfo]
    key: list[str]