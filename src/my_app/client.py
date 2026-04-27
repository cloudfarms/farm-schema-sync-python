import httpx
import csv
from my_app.config import Config
from my_app.models import AuthRequest, AuthResponse, TableInfo, OrgHolding, SectionItem, SyncItem
from my_app.enums import State, CsvOperation
from typing import Optional, Union
from my_app.pipelineChannel import PipelineChannel 
from my_app.transforms import Transforms

class Client:
    """
        Handles all request to the swagger API
    """
    def __init__(self, config:Config):
        self.config = config
        self.client = httpx.Client(base_url=config.baseUrl)
        self.state = State.START

    def authenticate(self):
        authReq = AuthRequest(clientId=self.config.clientId, clientSecret=self.config.clientSecret)
        response = self.client.post("/cfapi/auth", data=authReq.model_dump_json()) #type: ignore[reportArgumentType]
        if response.status_code != 200:
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
    
    async def holdingChangesProducer(self, path:str, since:Optional[str]):
        if since is not None:
            path = f"{path}?since={since}"
        self.state = State.START
        async with httpx.AsyncClient(base_url=self.config.baseUrl) as client:
            async with client.stream("GET", path, headers={"Accept": "text/csv", "Authorization": self.client.headers["Authorization"]}) as r:
                if r.status_code == 401:
                    raise Exception("Missing or invalid auth token")
                if r.status_code == 403:
                    raise Exception("No access")
                if not r.is_success:
                    raise Exception(f"Something went wrong")
                async for line in r.aiter_lines():
                    if line:
                        """
                        Add logic for metadata header, then metadata rows 
                        """
                        parsed = self.parseLine(line)
                        if parsed is not None:
                            await self.channel.queue.put(parsed)
            await self.channel.queue.put(None)
    
    def parseLine(self, line:Optional[str]) -> Optional[Union[SectionItem, SyncItem]]:
        """
        Parses lines to more easily readable stuff for consumer. If return is None, line is ignored 
        """
        if self.state == State.START:
            if line is None:
                raise Exception("Invalid CSV Response: empty body")
            if line.strip() != "data":
                raise Exception(f"Invalid CSV Response: expected first line to be \"data\", got {line}")
            self.state = State.METADATA_HEADER
            return None

        if not line:
            return None

        line = line.strip()

        if line == "*":
            return None

        if len(line.split(",")) == 1 and len(line.split("_")) > 1:
            self.state = State.SECTION_NAME

        if self.state == State.METADATA_HEADER:
            self.state = State.METEDATA_ROW
            self.channel.updateHeader = list(csv.reader([line]))[0] # save update data for later
            return None
        
        if self.state == State.METEDATA_ROW:
            self.state = State.WAIT
            self.channel.updateRow = list(csv.reader([line]))[0] # save update data for later
            return None

        if self.state == State.SECTION_NAME:
            operation = line.split("_")[-1]
            tableName = "_".join(line.split("_")[:-1])
            self.state = State.HEADER
            return {"type": State.SECTION_NAME, "table": tableName , "operation": CsvOperation(operation)}

        if self.state == State.HEADER:
            self.state = State.ROWS
            return {"type" : State.HEADER, "data": list(csv.reader([line]))[0]}
        
        if self.state == State.ROWS:
            # take into account partial lines, which can be in quotes
            parsed, isDone = Transforms.parseCsvLine(line, self.buffer is not None, self.buffer)
            if isDone:
                return {"type": State.ROWS, "data": parsed}
            else:
                self.buffer = parsed
                return None


    
    def setChannel(self, channel: PipelineChannel):
        self.channel = channel
        self.buffer = None