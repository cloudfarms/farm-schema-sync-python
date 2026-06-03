from pydantic import BaseModel

class AuthResponse(BaseModel):
    token: str
    validFrom: str
    validTo: str