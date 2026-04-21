from pydantic import BaseModel
from typing import Optional
class OrgFarm(BaseModel):
    id: int
    name: str
    farm_type: str
    time_zone: str
    external_id: Optional[str]
    customers_id:Optional[str]
    internal_name: Optional[str]
