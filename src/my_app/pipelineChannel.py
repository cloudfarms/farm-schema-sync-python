from asyncio import Queue
from my_app.models import SyncItem, SectionItem

class PipelineChannel:
    def __init__(self):
        self.queue: Queue[SyncItem | SectionItem] = Queue(maxsize=1000)