from config import Config
import httpx
from models import AuthRequest
from models import AuthResponse, TableInfo

class Client:

    def __init__(self, config:Config):
        self.config = config
        self.client = httpx.Client(base_url=config.baseUrl)

    def authenticate(self):
        authReq = AuthRequest(clientId=self.config.clientId, clientSecret=self.config.clientSecret)
        response = self.client.post("/cfapi/auth", data=authReq.model_dump_json())
        if response.status_code != 200:
            raise Exception("incorrect credentials")
        if not response.is_success:
            raise Exception("Authentication failed")
        auth = AuthResponse.model_validate(response.json())
        self.client.headers["Authorization"] = f"Bearer {auth.token}"
    
    def getAllTables(self):
        # needs to get both farm tables and holdings table
        farmTables = self.getTables("/cfapi/farm/data-changes/tables")
        holdingTables = self.getTables("/cfapi/holding/data-changes/tables")
        return farmTables + holdingTables

    def getTables(self, path: str):
        response = self.client.get(f"{path}")
        if response.status_code == 401:
            raise Exception("Missing or invalid auth token")
        if response.status_code == 400:
            raise Exception("No access")
        if not response.is_success:
            raise Exception(f"Could not get tables from {path}")
        
        return [TableInfo.model_validate(item) for item in response.json()]