from asyncio import Queue
from my_app.models import SyncItem, SectionItem, DataSyncResult
from typing import Union, Optional


class PipelineChannel:
    def __init__(self):
        self.queue: Queue[Optional[Union[SyncItem,SectionItem]]] = Queue(maxsize=1000)
        self.results: DataSyncResult = {"rowsDeleted": 0, "rowsUpserted": 0}
        self.updateHeader: list[str]
        self.updateRow: list[str]