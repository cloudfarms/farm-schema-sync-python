from pydantic import BaseModel

class PythonColumnInfo(BaseModel):
    name: str
    typeName: type

