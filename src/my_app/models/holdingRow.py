from pydantic import BaseModel
from typing import Optional
class HoldingRow(BaseModel):
    id: int
    name: str
    parentId: Optional[int] = None
    externalId: Optional[str] = None
    customersId: Optional[str] = None
    internalName: Optional[str] = None
