import asyncio
from my_app.pipelineChannel import PipelineChannel
from my_app.client import Client
from my_app.database import Database

class AsyncController:
    def __init__(self, apiClient: Client, dbClient: Database):
        self.channel = PipelineChannel()
        apiClient.setChannel(self.channel)
        dbClient.setChannel(self.channel)
        self.producer = apiClient
        self.consumer = dbClient

    async def run(self, url:str, since: str):
        await asyncio.gather(self.producer.holdingChangesProducer(url, since), self.consumer.applyDataChangesConsumer())