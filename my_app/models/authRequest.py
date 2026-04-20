from pydantic import BaseModel

class AuthRequest(BaseModel):
    clientId: str
    clientSecret: str