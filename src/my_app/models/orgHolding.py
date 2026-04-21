from __future__ import annotations
from pydantic import BaseModel
from my_app.models import OrgFarm
from typing import Optional

class OrgHolding(BaseModel):
    id: int
    name: str
    parentId: Optional[int] = None
    externalId: Optional[str] = None
    customersId: Optional[str] = None
    internalName: Optional[str] = None
    farms: Optional[list[OrgFarm]] = None
    subholdings: Optional[list[OrgHolding]] = None
