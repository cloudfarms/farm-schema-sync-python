from pydantic import BaseModel

class ServerDbConfig(BaseModel):
    dbName: str
    dbHost: str
    dbPort: int
    dbUser: str
    dbPassword: str

class SqliteDbConfig(BaseModel):
    dbName: str