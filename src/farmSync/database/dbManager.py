from typing import Union, Optional, cast
from collections.abc import Callable
from farmSync.core.enums import Dialect, CsvOperation, State
from farmSync.models import TableInfo, SchemaResults, HoldingRow, FarmRow, OrgSyncResult
from farmSync.models import ServerDbConfig, SqliteDbConfig, SectionItem, SyncItem
from farmSync.core.pipelineChannel import PipelineChannel
from farmSync.database.queries import SqliteGenerator, PostgresGenerator
from farmSync.database.queries import MsSqlGenerator, MySqlGenerator
import sqlite3
import psycopg2
from psycopg2.extras import execute_values
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
        self.channel: PipelineChannel = None # type: ignore
        self.dialect = dialect
        self.conn, self.cursor, self.generator = self._establishConnection(dialect, config)
        self._upsert = self._getUpsertFunc(dialect)
        self.typeCache: dict[str, dict[str, str]] = {}
        self.pkCache: dict[str, list[str]] = {}
    
    def _establishConnection(self, dialect: Dialect, config: Union[ServerDbConfig, SqliteDbConfig]
                             ) -> tuple[Connection, Cursor, Generator]:
        """
            Establishes a connection to the appropriate database. Returns the connection, cursor,
            and generator based on the database dialect
        """
        if dialect == Dialect.SQLITE:
            conn = sqlite3.connect(config.dbName)
            cursor = conn.cursor()
            generator = SqliteGenerator()
            return conn, cursor, generator

        config = cast(ServerDbConfig, config)
        if dialect == Dialect.POSTGRES:
            conn = psycopg2.connect(host=config.dbHost, port=config.dbPort,
                                         dbname=config.dbName, user=config.dbUser,
                                         password=config.dbPassword)
            cursor = conn.cursor()
            generator = PostgresGenerator()
            return conn, cursor, generator
        if dialect == Dialect.MYSQL:
            conn = mysql.connect(host=config.dbHost, port=config.dbPort,
                                      database=config.dbName, user=config.dbUser,
                                      password=config.dbPassword, collation="utf8mb4_bin",
                                      charset="utf8mb4")
            cursor = conn.cursor(dictionary=False)
            generator = MySqlGenerator()
            return conn, cursor, generator
        if dialect == Dialect.MSSQL:
            server = f"Server={config.dbHost},{config.dbPort};"
            database = f"Database={config.dbName};"
            authentication = f"UID={config.dbUser};PWD={config.dbPassword};"
            settings = "TrustServerCertificate=yes;"
            connectionString = server + database + authentication + settings
            conn = mssql_python.connect(connectionString)
            cursor = conn.cursor()
            generator = MsSqlGenerator()
            return conn, cursor, generator
        raise Exception("Unknown dialect")

    def _getUpsertFunc(self, dialect: Dialect) -> Callable[[str, list[str], list[tuple]], None]: 
        mapping = {
            Dialect.SQLITE: self._sqliteUpsert,
            Dialect.POSTGRES: self._postgresUpsert,
            Dialect.MYSQL: self._mysqlUpsert,
            Dialect.MSSQL: self._mssqlUpsert
        }
        if dialect in mapping:
            return mapping[dialect]
        raise Exception("Unknown dialect")
    

    def execSchema(self, tables: list[TableInfo]) -> SchemaResults:
        """
            Creates all the tables in the database 
        """
        results: SchemaResults = {"tablesCreated": 0, "tablesExisting": 0, "colsAdded": 0}
        for table in tables:
            exists = self._tableExists(table.name)
            if exists:
                self.pkCache[table.name] = table.key
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
                self.conn.rollback()
                raise Exception(f"Failed to create table {table.name}: {e}")
        return results
    
    def syncOrgData(self,holdingRows: list[HoldingRow], farmRows: list[FarmRow])-> OrgSyncResult:
        """
            Creates and updates all the holdings and farms that are in the database to reflect
            what the user has access to. 
        """
        HOLDING_DDL = self.generator.getHoldingDdl()
        FARM_DDL = self.generator.getFarmDdl()
        try:
            self.cursor.execute(HOLDING_DDL)
        except Exception as e:
            self.conn.rollback()
            raise Exception(f"Failed to create table holding: {e}")
        try:
            self.cursor.execute(FARM_DDL)
        except Exception as e:
            self.conn.rollback()
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
                self.conn.rollback()
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
                self.conn.rollback()
                raise Exception(f"Failed to upsert farm {farm.id}: {e}")
        self.conn.commit()
        return {"holdingsUpserted": holdingsUpserted, "farmsUpserted": farmsUpserted}

    def readHoldingIds(self)-> list[tuple[int, Optional[str]]]:
        """
            Returns all the holdings that the user has access to 
        """
        try:
            query = self.generator.getHoldingIdsQuery()
            self.cursor.execute(query)
            rows = self.cursor.fetchall()
            return rows # type: ignore
        except Exception as e:
            raise Exception(f"Failed to collect holding IDs: {e}")

    def readFarmIds(self) -> list[tuple[int, Optional[str]]]:
        """
            Returns all the farms that the user has access to 
        """
        try:
            query = self.generator.getFarmIdsQuery()
            self.cursor.execute(query)
            rows = self.cursor.fetchall()
            return rows # type: ignore
        except Exception as e:
            raise Exception(f"Failed to collect farm IDs: {e}")

    async def applyDataChangesConsumer(self):
        """
            Consumes the data changes queue and applies the changes to the database 
        """
        batch = []
        tableName: Optional[str] = None 
        sections: Optional[list[str]] = None 
        operation: Optional[CsvOperation] = None 
        while True:
            item = await self.channel.queue.get()
            if item is None:
                break
            
            if item["type"] == State.SECTION_NAME:
                item = cast(SectionItem, item) 
                batch = self._flushBatch(tableName, operation, sections, batch)
                tableName = item["table"]
                operation = item["operation"]
                continue

            if item["type"] == State.HEADER:
                item = cast(SyncItem, item)
                sections = list(cast(list[str], item["data"]))
                continue

            if item["type"] == State.ROWS:
                item = cast(SyncItem, item)
                batch.append(item["data"])
                if len(batch) >= 5000:
                    batch = self._flushBatch(tableName, operation, sections, batch)
                continue
        self._flushBatch(tableName, operation, sections, batch)
        self.conn.commit()
    
    def _flushBatch(self, tableName: Optional[str], operation: Optional[CsvOperation],
                    sections: Optional[list[str]], batch: list[tuple]):
        """
            Applies the data changes and clears the batch. 
        """
        if len(batch) == 0:
            return batch
        if tableName is not None and operation is not None and sections is not None:
            self._applyDataChange(tableName, operation, sections, batch)
            return []
        else:
            raise Exception("could not apply change as some values are None")
   
    def _applyDataChange(self, tableName:str, operation: CsvOperation, sections: list[str],
                         batch: list[tuple]):
        """
            Applies the data change to the database
        """
        if operation == CsvOperation.UPSERT:
            self._upsert(tableName, sections, batch)
            self.channel.results["rowsUpserted"] += len(batch)
        elif operation == CsvOperation.DELETE:
            self._delete(tableName, sections, batch)
            self.channel.results["rowsDeleted"] += len(batch)
        else:
            raise Exception(f"Unknown operation type: {operation}")
    
    def _sqliteUpsert(self, tableName: str, sections: list[str], values: list[tuple]):
        self.generator = cast(SqliteGenerator, self.generator)
        sql = self.generator.getUpsertQuery(tableName, sections)
        try:
            self.cursor.executemany(sql, values) # type: ignore
        except Exception as e:
            self.conn.rollback()
            raise Exception(f"Upserting failed: {e}")

    def _postgresUpsert(self, tableName: str, sections: list[str], values: list[tuple]):
        try:
            primaries = set(self.pkCache[tableName])
        except Exception:
            raise Exception(f"Failed to get primary keys for table {tableName}")

        self.generator = cast(PostgresGenerator, self.generator)
        sql = self.generator.getUpsertQuery(tableName, sections, primaries)

        try:
            execute_values(self.cursor, sql, values)
        except Exception as e:
            self.conn.rollback()
            raise Exception(f"row does not match structure: {e}")
    

    def _mysqlUpsert(self, tableName: str, sections: list[str], values: list[tuple]):
        try:
            primaries = set(self.pkCache[tableName])
        except:
            raise Exception(f"Failed to get primary keys for table {tableName}")

        self.generator = cast(MySqlGenerator, self.generator)
        sql = self.generator.getUpsertQuery(tableName, sections, primaries)
        try:
            self.cursor.executemany(sql, values) # type: ignore
        except Exception as e:
            self.conn.rollback()
            raise Exception(f"row does not match structure: {e}")
    
    def _mssqlUpsert(self, tableName: str, sections: list[str], values: list[tuple]):
        self.generator = cast(MsSqlGenerator, self.generator)
        try:
            primaries = set(self.pkCache[tableName])
            types = self.typeCache[tableName]
        except Exception as e:
            self.conn.rollback()
            raise Exception(f"Failed to get cached data for table {tableName}: {e}")

        tempTable, createStagingSql = self.generator.getTempTableQuery(tableName, sections, types)

        mergeSql = self.generator.getUpsertQuery(tableName, sections, primaries, tempTable)
        try:
            self.cursor.execute(createStagingSql)
            self.conn.commit() # bulkcopy creates a new connection and needs to see the temporary table
            self.cursor.bulkcopy(tempTable, values, table_lock=True, batch_size=5000, timeout=120) # type: ignore
            self.cursor.execute(mergeSql)
            self.cursor.execute(f"DROP TABLE {self.generator._quoteIdent(tempTable)}")
        except Exception as e:
            self.conn.rollback()
            self.cursor.execute(f"IF OBJECT_ID('tempdb..{tempTable}') IS NOT NULL "
                                f"DROP TABLE {self.generator._quoteIdent(tempTable)}")
            self.conn.commit()
            raise Exception(f"Issue in table {tableName}: {e}")

    def _delete(self, tableName: str, sections: list[str], values: list[tuple]):
        placeholder = self.generator.placeholder
        whereClauses = [f"{self.generator._quoteIdent(where)} = {placeholder}" for where in sections]
        sql = f"DELETE FROM {self.generator._quoteIdent(tableName)} WHERE {' AND '.join(whereClauses)}"
        if self.dialect == Dialect.SQLITE:
            # sqlite has a limit of 1000 parameters
            chunkSize = 990 // max(1, len(sections))
            for i in range(0, len(values), chunkSize):
                self.cursor.executemany(sql, values[i:i + chunkSize]) # type: ignore
        else:
            self.cursor.executemany(sql, values) # type: ignore

    def _getExistingCols(self,tableName:str) -> list[str]:
        query, params, colIndices = self.generator.getExistingColsQuery(tableName)
        try: 
            typeCache = {}
            nameIndex, typeIndex = colIndices
            self.cursor.execute(query, params)
            rows = self.cursor.fetchall()
            allCols = []
            for row in rows:
                colName = str(row[nameIndex]) # type: ignore
                colType = str(row[typeIndex]) # type: ignore
                typeCache[colName] = colType
                allCols.append(colName)
            self.typeCache[tableName] = typeCache
            return allCols
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
    
    def updateHoldingMetadata(self, holdingId: int, lastSince: Optional[str], nextSince: Optional[str]):
        """
            Update the metadata for a holding
        """
        sql = self.generator.getUpdateHoldingMetaQuery()
        self.cursor.execute(sql, (lastSince, nextSince, holdingId))
        self.conn.commit()
    
    def updateFarmMetadata(self, farmId: int, lastSince: Optional[str], nextSince: Optional[str]):
        """
            Update the metadata for a farm
        """
        sql = self.generator.getUpdateFarmMetaQuery()
        self.cursor.execute(sql, (lastSince, nextSince, farmId))
        self.conn.commit()