from pydantic import BaseModel
class FarmRow(BaseModel):
    id: int
    name: str
    holding_id: int
    farm_type: str
    time_zone: str
    external_id: str | None
    customers_id: str | None
    internal_name: str | None
