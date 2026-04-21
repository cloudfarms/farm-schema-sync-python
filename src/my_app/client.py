from my_app.config import Config
import httpx
from my_app.models import AuthRequest, AuthResponse, TableInfo, OrgHolding

class Client:
    """
        Handles all request to the swagger API
    """
    def __init__(self, config:Config):
        self.config = config
        self.client = httpx.Client(base_url=config.baseUrl)

    def authenticate(self):
        authReq = AuthRequest(clientId=self.config.clientId, clientSecret=self.config.clientSecret)
        response = self.client.post("/cfapi/auth", json=authReq.model_dump_json())
        if response.status_code != 200:
            raise Exception("incorrect credentials")
        if not response.is_success:
            raise Exception("Authentication failed")
        auth = AuthResponse.model_validate(response.json())
        self.client.headers["Authorization"] = f"Bearer {auth.token}"
    
    def getAllTables(self) -> list[TableInfo]:
        # needs to get both farm tables and holdings table
        farmTables = self.getTables("/cfapi/farm/data-changes/tables")
        holdingTables = self.getTables("/cfapi/holding/data-changes/tables")
        return farmTables + holdingTables

    def getTables(self, path: str) -> list[TableInfo]:
        response = self.client.get(f"{path}")
        if response.status_code == 401:
            raise Exception("Missing or invalid auth token")
        if response.status_code == 400:
            raise Exception("No access")
        if not response.is_success:
            raise Exception(f"Could not get tables from {path}")
        
        return [TableInfo.model_validate(item) for item in response.json()]
    
    def getHoldings(self)-> list[OrgHolding]:
        response = self.client.get("/cfapi/org/holdings")
        if response.status_code == 401:
            raise Exception("Missing or invalid auth token")
        if not response.is_success:
            raise Exception(f"Failed to get holdings")
        return [OrgHolding.model_validate(item) for item in response.json()]