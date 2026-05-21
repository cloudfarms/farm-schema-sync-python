from pydantic import BaseModel
from farmSync.models import PythonColumnInfo

class PythonTableInfo(BaseModel):
    name: str
    columns: list[PythonColumnInfo]
    key: list[str]