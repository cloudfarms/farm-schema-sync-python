import httpx
from farmSync.config import Config
from farmSync.models import AuthRequest, AuthResponse, TableInfo, OrgHolding,PythonTableInfo
from farmSync.core.enums import State
from typing import Optional
from farmSync.core.pipelineChannel import PipelineChannel
from farmSync.core.csvParser import CsvParser

class Client:
    """
        Handles all request to the swagger API
    """
    def __init__(self, config:Config):
        self.config = config
        self.client = httpx.Client(base_url=config.baseUrl)
        self.state = State.START
        self.channel: Optional[PipelineChannel] = None

    def authenticate(self):
        print("Authenticating...")
        authReq = AuthRequest(clientId=self.config.clientId, clientSecret=self.config.clientSecret)
        # using json= for some reason doesn't work with JSON and data= works?
        response = self.client.post("/cfapi/auth", data=authReq.model_dump_json()) #type: ignore[reportArgumentType]
        if response.status_code == 401:
            raise Exception("incorrect credentials")
        if not response.is_success:
            raise Exception("Authentication failed")
        auth = AuthResponse.model_validate(response.json())
        self.client.headers["Authorization"] = f"Bearer {auth.token}"
    
    def getAllTables(self) -> list[TableInfo]:
        # needs to get both farm tables and holdings table
        farmTables = self._getTables("/cfapi/farm/data-changes/tables")
        holdingTables = self._getTables("/cfapi/holding/data-changes/tables")
        return farmTables + holdingTables

    def _getTables(self, path: str) -> list[TableInfo]:
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
    
    async def holdingChangesProducer(self, path:str, since:Optional[str], tableMap: dict[str, PythonTableInfo]):
        if since is not None:
            path = f"{path}?since={since}"
        if self.channel is None:
            raise Exception("Channel not set")
        parser = CsvParser(self.channel)

        headers = {
            "Accept": "text/csv",
            "Authorization": self.client.headers["Authorization"]
        }
        try:
            async with httpx.AsyncClient(base_url=self.config.baseUrl, timeout=60.0) as client:
                async with client.stream("GET", path, headers=headers) as r:
                    if r.status_code == 401:
                        raise Exception(f"Missing or invalid auth token: {path}")
                    if r.status_code == 403:
                        raise Exception(f"No access: {path}")
                    if not r.is_success:
                        raise Exception(f"Something went wrong: {path}")
                    async for line in r.aiter_lines():
                        if line:
                            """
                            Add logic for metadata header, then metadata rows 
                            """
                            parsed = parser.parseLine(line)
                            if parsed is not None:
                                parsed = parser.translateToPython(parsed, tableMap)
                                await self.channel.queue.put(parsed)
        finally:
            await self.channel.queue.put(None)
    
    def setChannel(self, channel: PipelineChannel):
        self.channel = channel
        self.buffer = None