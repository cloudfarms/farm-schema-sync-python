from pydantic import BaseModel
from my_app.models import PythonColumnInfo

class PythonTableInfo(BaseModel):
    name: str
    columns: list[PythonColumnInfo]
    key: list[str]