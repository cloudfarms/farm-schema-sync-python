from typing import Union, Optional, cast
from farmSync.core.enums import Dialect, CsvOperation
from farmSync.models import TableInfo, SchemaResults, HoldingRow, FarmRow, OrgSyncResult
from farmSync.models import ServerDbConfig, SqliteDbConfig
from farmSync.core import PipelineChannel
from farmSync.database.queries import MsSqlGenerator, MySqlGenerator, SqliteGenerator, PostgresGenerator

class DbManager:

    def __init__(self, config: Union[ServerDbConfig, SqliteDbConfig], dialect: Dialect) -> None:
        self.config = config
        self.channel = None
        self.database = self._getDatabase(dialect, config)
        self.dialect = self.database.dialect
        self.cursor = self.database.cursor
        self.conn = self.database.conn

        self.typeCache: dict[str, dict[str, str]] = {}
        self.pkCache: dict[str, list[str]] = {}
    
    def _getDatabase(self, dialect: Dialect, config: Union[ServerDbConfig, SqliteDbConfig]):
        if dialect == Dialect.SQLITE:
            config = cast(SqliteDbConfig, config)
            return SqliteGenerator(config)
        if dialect == Dialect.POSTGRES:
            config = cast(ServerDbConfig, config)
            return PostgresGenerator(config)
        if dialect == Dialect.MYSQL:
            config = cast(ServerDbConfig, config)
            return MySqlGenerator(config)
        if dialect == Dialect.MSSQL:
            config = cast(ServerDbConfig, config)
            return MsSqlGenerator(config)
        raise Exception("Unknown dialect")

    def execSchema(self, tables: list[TableInfo]) -> SchemaResults:
        results: SchemaResults = {"tablesCreated": 0, "tablesExisting": 0, "colsAdded": 0}
        for table in tables:
            exists = self._tableExists(table.name)
            if exists:
                existing = self._getExistingCols(table.name)
                added = self._addMissingCols(table, existing)
                if added > 0:
                    print(f"Table {table.name} updated with {added} new cols")
                else:
                    print(f"Table {table.name} is already up to date")
                results["colsAdded"] += added
                results["tablesExisting"] += 1
                continue
            try:
                self._generateTable(table)
                results["tablesCreated"] += 1
            except Exception as e:
                raise Exception(f"Failed to create table {table.name}: {e}")
        return results
    
    def syncOrgData(self,holdingRows: list[HoldingRow], farmRows: list[FarmRow])-> OrgSyncResult:
        pass

    def readHoldingIds(self)-> list[tuple[int, Optional[str]]]:
        pass

    def readFarmIds(self) -> list[tuple[int, Optional[str]]]:
        pass

    async def applyDataChangesConsumer(self):
        pass
   
    def _applyDataChange(self, tableName:str, operation: CsvOperation, sections: list[str],
                          batch: list[list]):
        pass
    
    def _upsert(self, tableName: str, sections: list[str], values: list[list]):
        pass

    def _delete(self, tableName: str, sections: list[str], values: list[list]):
        pass

    def updateHoldingMetadata(self, holdingId: int, lastSince: Optional[str],
                              nextSince: Optional[str]):
        pass

    def updateFarmMetadata(self, farmId: int, lastSince: Optional[str], nextSince: Optional[str]):
        pass

    def _getExistingCols(self,tableName:str) -> list[str]:
        query, params, colIndex = self.database.getExistingColsQuery(tableName)
        try: 
            self.cursor.execute(query, params)
            rows = self.cursor.fetchall()
            return [str(row[colIndex]) for row in rows] # type: ignore
        except Exception as e:
            raise Exception(f"Failed to read columns for {tableName}: {e}")
    
    def _addMissingCols(self, table: TableInfo, existing: list[str]) -> int:
        added = 0
        queries = self.database.getAddColQueries(table, existing)
        for query, colName in queries:
            try:
                self.cursor.execute(query)
                self.conn.commit()
                print(f'Added col {colName} to {table.name}')
                added += 1
            except Exception as e:
                raise Exception(f"failed to add column {colName} into {table.name}: {e}")
        return added

    def _tableExists(self,tableName: str) -> bool:
        query = self.database.getTableExistQuery()
        self.cursor.execute(query, (tableName,))
        result = self.cursor.fetchone()
        if result is None:
            return False
        if isinstance(result, (tuple, list)):
            return bool(result[0])
        return bool(result)

    def _generateTable(self,table: TableInfo) -> None:
        query, typeCache = self.database.getNewTableQuery(table)
        self.cursor.execute(query)
        self.conn.commit()
        self.typeCache[table.name] = typeCache
        self.pkCache[table.name] = table.key


    def setChannel(self, channel: PipelineChannel)->None:
        self.channel = channel