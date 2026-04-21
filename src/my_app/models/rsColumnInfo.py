from pydantic import BaseModel

class RsColumnInfo(BaseModel):
    name: str
    jdbcType: int
    dbTypeName: str
    scale: int
    precision: int

