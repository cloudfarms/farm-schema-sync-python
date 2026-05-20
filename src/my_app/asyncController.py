import asyncio
from typing import Optional
from my_app.pipelineChannel import PipelineChannel
from my_app.client import Client
from my_app.db import Database
from my_app.models import PythonTableInfo

class AsyncController:
    def __init__(self, apiClient: Client, dbClient: Database, tableMap: dict[str, PythonTableInfo]):
        self.channel = PipelineChannel(dbClient.dialect)
        apiClient.setChannel(self.channel)
        dbClient.setChannel(self.channel)
        self.producer = apiClient
        self.consumer = dbClient
        self.tableMap = tableMap

    async def run(self, url:str, since: Optional[str]):
        await asyncio.gather(self.producer.holdingChangesProducer(url, since, self.tableMap), self.consumer.applyDataChangesConsumer(), return_exceptions=True)