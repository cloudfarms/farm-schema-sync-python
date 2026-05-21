import asyncio
from typing import Optional
from farmSync.core import PipelineChannel
from farmSync.client import Client
from farmSync.database import DbManager
from farmSync.models import PythonTableInfo

class AsyncController:
    def __init__(self, apiClient: Client, dbClient: DbManager, tableMap: dict[str, PythonTableInfo]):
        self.channel = PipelineChannel(dbClient.dialect)
        apiClient.setChannel(self.channel)
        dbClient.setChannel(self.channel)
        self.producer = apiClient
        self.consumer = dbClient
        self.tableMap = tableMap

    async def run(self, url:str, since: Optional[str]):
        await asyncio.gather(self.producer.holdingChangesProducer(url, since, self.tableMap),
                             self.consumer.applyDataChangesConsumer(), return_exceptions=True)