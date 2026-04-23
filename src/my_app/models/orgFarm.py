from pydantic import BaseModel
from typing import Optional
class OrgFarm(BaseModel):
    id: int
    name: str
    farmType: str
    timeZone: str
    externalId: Optional[str] = None
    customersId:Optional[str] = None
    internalName: Optional[str] = None
