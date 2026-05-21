from asyncio import Queue
from farmSync.models import SyncItem, SectionItem, DataSyncResult
from typing import Union, Optional
from farmSync.core.enums import Dialect


class PipelineChannel:
    def __init__(self, dialect: Dialect):
        self.queue: Queue[Optional[Union[SyncItem,SectionItem]]] = Queue(maxsize=1000)
        self.results: DataSyncResult = {"rowsDeleted": 0, "rowsUpserted": 0}
        self.updateHeader: list[str] = []
        self.updateRow: list[str] = []
        self.dialect = dialect