from pydantic import BaseModel
from typing import Optional

class FarmRow(BaseModel):
    id: int
    name: str
    holdingId: int
    farmType: str
    timeZone: str
    externalId: Optional[str] = None
    customersId: Optional[str] = None
    internalName: Optional[str] = None
