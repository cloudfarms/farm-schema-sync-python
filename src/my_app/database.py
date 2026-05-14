from my_app.models import ServerDbConfig, SqliteDbConfig, SchemaResults, TableInfo, HoldingRow, FarmRow, OrgSyncResult
from my_app.enums import CsvOperation, Dialect
from typing import Optional, Union
from my_app.pipelineChannel import PipelineChannel
from abc import ABC, abstractmethod

class Database(ABC):

    @abstractmethod
    def __init__(self,config:Union[ServerDbConfig, SqliteDbConfig], dialect:Dialect):
        pass

    @abstractmethod
    def execSchema(self, tables: list[TableInfo]) -> SchemaResults:
        pass
    
    @abstractmethod
    def syncOrgData(self,holdingRows: list[HoldingRow], farmRows: list[FarmRow])-> OrgSyncResult:
        pass

    @abstractmethod
    def readHoldingIds(self)-> list[tuple[int, Optional[str]]]:
        pass

    @abstractmethod
    def readFarmIds(self) -> list[tuple[int, Optional[str]]]:
        pass

    @abstractmethod
    async def applyDataChangesConsumer(self):
        pass
   
    @abstractmethod
    def _applyDataChange(self, tableName:str, operation: CsvOperation, sections: list[str], batch: list[list]):
        pass
    
    @abstractmethod
    def _upsert(self, tableName: str, sections: list[str], values: list[list]):
        pass

    @abstractmethod
    def _delete(self, tableName: str, sections: list[str], values: list[list]):
        pass

    @abstractmethod
    def updateHoldingMetadata(self, holdingId: int, lastSince: Optional[str], nextSince: Optional[str]):
        pass

    @abstractmethod
    def updateFarmMetadata(self, farmId: int, lastSince: Optional[str], nextSince: Optional[str]):
        pass

    @abstractmethod
    def _getExistingCols(self,tableName:str) -> list[str]:
        pass
    
    @abstractmethod
    def _addMissingCols(self, table: TableInfo, existing: list[str]) -> int:
        pass

    @abstractmethod
    def _tableExists(self,tableName: str) -> bool:
        pass

    @abstractmethod
    def _generateTable(self,table: TableInfo) -> None:
        pass
        
    @abstractmethod
    def _quoteIdent(self, name: str) -> str:
        pass

    def setChannel(self, channel: PipelineChannel)->None:
        self.channel = channel