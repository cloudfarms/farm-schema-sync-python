from __future__ import annotations
from pydantic import BaseModel
from my_app.models import OrgFarm
from typing import Optional

class OrgHolding(BaseModel):
    id: int
    name: str
    parent_id: Optional[int]
    external_id: Optional[str]
    customers_id: Optional[str]
    internal_name: Optional[str]
    farms: Optional[list[OrgFarm]]
    subholdings: Optional[list[OrgHolding]]
