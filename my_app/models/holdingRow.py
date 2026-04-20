from pydantic import BaseModel
class HoldingRow(BaseModel):
    id: int
    name: str
    parent_id: int | None
    external_id: str | None
    customers_id: str | None
    internal_name: str | None
