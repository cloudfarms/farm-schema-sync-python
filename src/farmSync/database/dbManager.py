from typing import Union, Optional, cast
from farmSync.core.enums import Dialect, CsvOperation
from farmSync.models import TableInfo, SchemaResults, HoldingRow, FarmRow, OrgSyncResult
from farmSync.models import ServerDbConfig, SqliteDbConfig
from farmSync.core.pipelineChannel import PipelineChannel
from farmSync.database.queries import SqliteGenerator, PostgresGenerator
from farmSync.database.queries import MsSqlGenerator, MySqlGenerator
# database libraries
import sqlite3
import psycopg2
# from psycopg2.extras import execute_values
import mysql.connector as mysql
import mssql_python

from mysql.connector.abstracts import MySQLConnectionAbstract, MySQLCursorAbstract
from mysql.connector.pooling import PooledMySQLConnection

Generator = Union[SqliteGenerator, PostgresGenerator, MySqlGenerator, MsSqlGenerator]
Connection = Union[sqlite3.Connection, psycopg2.extensions.connection,
                   MySQLConnectionAbstract, PooledMySQLConnection, mssql_python.Connection]
Cursor = Union[sqlite3.Cursor, psycopg2.extensions.cursor,
               MySQLCursorAbstract, mssql_python.Cursor]
class DbManager:

    def __init__(self, config: Union[ServerDbConfig, SqliteDbConfig], dialect: Dialect) -> None:
        self.config = config
        self.channel = None
        self.dialect = dialect
        self.cursor: Cursor = None # type: ignore
        self.conn: Connection = None # type: ignore
        self.generator: Generator = None # type: ignore
        self._establishConnection(dialect, config)

        self.typeCache: dict[str, dict[str, str]] = {}
        self.pkCache: dict[str, list[str]] = {}
    
    def _establishConnection(self, dialect: Dialect, config: Union[ServerDbConfig, SqliteDbConfig]):
        if dialect == Dialect.SQLITE:
            self.conn = sqlite3.connect(config.dbName)
            self.cursor = self.conn.cursor()
            self.generator = SqliteGenerator()
            return
        if dialect == Dialect.POSTGRES:
            config = cast(ServerDbConfig, config)
            self.conn = psycopg2.connect(host=config.dbHost, port=config.dbPort,
                                         dbname=config.dbName, user=config.dbUser,
                                         password=config.dbPassword)
            self.cursor = self.conn.cursor()
            self.generator = PostgresGenerator()
            return
        if dialect == Dialect.MYSQL:
            config = cast(ServerDbConfig, config)
            self.conn = mysql.connect(host=config.dbHost, port=config.dbPort,
                                      database=config.dbName, user=config.dbUser,
                                      password=config.dbPassword)
            self.cursor = self.conn.cursor(dictionary=False)
            self.generator = MySqlGenerator()
            return
        if dialect == Dialect.MSSQL:
            config = cast(ServerDbConfig, config)
            server = f"Server={config.dbHost},{config.dbPort};"
            database = f"Database={config.dbName};"
            authentication = f"UID={config.dbUser};PWD={config.dbPassword};"
            settings = "TrustServerCertificate=yes;"
            connectionString = server + database + authentication + settings
            self.conn = mssql_python.connect(connectionString)
            self.cursor = self.conn.cursor()
            self.generator = MsSqlGenerator()
            return
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
        HOLDING_DDL = self.generator.getHoldingDdl()
        FARM_DDL = self.generator.getFarmDdl()
        try:
            self.cursor.execute(HOLDING_DDL)
        except Exception as e:
            raise Exception(f"Failed to create table holding: {e}")
        try:
            self.cursor.execute(FARM_DDL)
        except Exception as e:
            raise Exception(f"Failed to create table holding: {e}")

        holdingInsertSql = self.generator.getHoldingInsertQuery() 
        holdingsUpserted = 0
        for hold in holdingRows:
            try:
                self.cursor.execute(holdingInsertSql,
                                    (hold.id, hold.name, hold.parentId, hold.externalId,
                                     hold.customersId, hold.internalName))
                holdingsUpserted += 1
            except Exception as e:
                raise Exception(f"Failed to upsert holding {hold.id}: {e}")
        
        farmInsertSql = self.generator.getFarmInsertQuery() 
        farmsUpserted = 0
        for farm in farmRows:
            try:
                self.cursor.execute(farmInsertSql,
                                    (farm.id, farm.name, farm.holdingId, farm.farmType,
                                     farm.timeZone, farm.externalId, farm.customersId,
                                     farm.internalName))
                farmsUpserted+=1
            except Exception as e:
                raise Exception(f"Failed to upsert farm {farm.id}: {e}")
        self.conn.commit()
        return {"holdingsUpserted": holdingsUpserted, "farmsUpserted": farmsUpserted}

    def readHoldingIds(self)-> list[tuple[int, Optional[str]]]:
        try:
            query = self.generator.getHoldingIdsQuery()
            self.cursor.execute(query)
            rows = self.cursor.fetchall()
            return rows # type: ignore
        except Exception as e:
            raise Exception(f"Failed to collect holding IDs: {e}")

    def readFarmIds(self) -> list[tuple[int, Optional[str]]]:
        try:
            query = self.generator.getFarmIdsQuery()
            self.cursor.execute(query)
            rows = self.cursor.fetchall()
            return rows # type: ignore
        except Exception as e:
            raise Exception(f"Failed to collect farm IDs: {e}")

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
        query, params, colIndex = self.generator.getExistingColsQuery(tableName)
        try: 
            self.cursor.execute(query, params)
            rows = self.cursor.fetchall()
            return [str(row[colIndex]) for row in rows] # type: ignore
        except Exception as e:
            raise Exception(f"Failed to read columns for {tableName}: {e}")
    
    def _addMissingCols(self, table: TableInfo, existing: list[str]) -> int:
        added = 0
        queries = self.generator.getAddColQueries(table, existing)
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
        query = self.generator.getTableExistQuery()
        self.cursor.execute(query, (tableName,))
        result = self.cursor.fetchone()
        if result is None:
            return False
        if isinstance(result, (tuple, list)):
            return bool(result[0])
        return bool(result)

    def _generateTable(self,table: TableInfo) -> None:
        query, typeCache = self.generator.getNewTableQuery(table)
        self.cursor.execute(query)
        self.conn.commit()
        self.typeCache[table.name] = typeCache
        self.pkCache[table.name] = table.key


    def setChannel(self, channel: PipelineChannel)->None:
        self.channel = channel