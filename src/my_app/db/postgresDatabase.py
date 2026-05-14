from my_app.db import Database
from my_app.models import ServerDbConfig, SchemaResults, FarmRow, HoldingRow, OrgSyncResult
from my_app.models import TableInfo, SectionItem, SyncItem
from my_app.enums import State, CsvOperation, Dialect
from typing import Optional, cast
from my_app.transforms import Transforms
import psycopg2
from psycopg2.extras import execute_values, execute_batch
from io import StringIO

class PostgresDatabase(Database[ServerDbConfig]):

    def __init__(self,config:ServerDbConfig)->None:
        self.conn = psycopg2.connect(host=config.dbHost, port=config.dbPort, dbname=config.dbName, user=config.dbUser, password=config.dbPassword)
        self.dialect = Dialect.POSTGRES
        self.cursor = self.conn.cursor()


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
        HOLDING_DDL = """
            CREATE TABLE IF NOT EXISTS "holding" (
            "id" BIGINT PRIMARY KEY,
            "name" TEXT,
            "parent_id" BIGINT,
            "external_id" TEXT,
            "customers_id" TEXT,
            "internal_name" TEXT,
            "active" BOOLEAN,
            "last_sync" TEXT,
            "last_since" TEXT,
            "next_since" TEXT
        )
        """
        FARM_DDL = """
            CREATE TABLE IF NOT EXISTS "farm" (
            "id" BIGINT PRIMARY KEY,
            "name" TEXT,
            "holding_id" BIGINT,
            "farm_type" TEXT,
            "time_zone" TEXT,
            "external_id" TEXT,
            "customers_id" TEXT,
            "internal_name" TEXT,
            "last_sync" TEXT,
            "last_since" TEXT,
            "next_since" TEXT
        )
        """
        try:
            self.cursor.execute(HOLDING_DDL)
        except Exception as e:
            raise Exception(f"Failed to create table holding: {e}")
        try:
            self.cursor.execute(FARM_DDL)
        except Exception as e:
            raise Exception(f"Failed to create table holding: {e}")
        
        holdingsUpserted = 0
        for hold in holdingRows:
            try:
                self.cursor.execute("""
                    INSERT INTO "holding" ("id", "name", "parent_id", "external_id", "customers_id", "internal_name")
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT ("id") DO UPDATE SET
                    "name" = EXCLUDED."name",
                    "parent_id" = EXCLUDED."parent_id",
                    "external_id" = EXCLUDED."external_id",
                    "customers_id" = EXCLUDED."customers_id",
                    "internal_name" = EXCLUDED."internal_name"
                                    """, (hold.id, hold.name, hold.parentId, hold.externalId, hold.customersId, hold.internalName))
                holdingsUpserted += 1
            except Exception as e:
                raise Exception(f"Failed to upsert holding {hold.id}: {e}")
        
        farmsUpserted = 0
        for farm in farmRows:
            try:
                self.cursor.execute("""
                    INSERT INTO "farm" ("id", "name", "holding_id", "farm_type", "time_zone", "external_id", "customers_id", "internal_name")
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO UPDATE SET
                    "name" = EXCLUDED."name",
                    "holding_id" = EXCLUDED."holding_id",
                    "farm_type" = EXCLUDED."farm_type",
                    "time_zone" = EXCLUDED."time_zone",
                    "external_id" = EXCLUDED."external_id",
                    "customers_id" = EXCLUDED."customers_id",
                    "internal_name" = EXCLUDED."internal_name"
                                    """, (farm.id, farm.name, farm.holdingId, farm.farmType, farm.timeZone, farm.externalId, farm.customersId, farm.internalName))
                farmsUpserted+=1
            except Exception as e:
                raise Exception(f"Failed to upsert farm {farm.id}: {e}")
        self.conn.commit()
        return {"holdingsUpserted": holdingsUpserted, "farmsUpserted": farmsUpserted}

    def readHoldingIds(self)-> list[tuple[int, Optional[str]]]:
        try:
            self.cursor.execute('SELECT "id", "next_since" FROM "holding" WHERE "parent_id" IS NULL')
            rows = self.cursor.fetchall()
            return rows
        except Exception as e:
            raise Exception(f"Failed to collect holding IDs: {e}")

    def readFarmIds(self) -> list[tuple[int, Optional[str]]]:
        try:
            self.cursor.execute('SELECT "id", "next_since" FROM "farm"')
            rows = self.cursor.fetchall()
            return rows
        except Exception as e:
            raise Exception(f"Failed to collect farm IDs: {e}")

    async def applyDataChangesConsumer(self):
        batch = []
        tableName: Optional[str] = None 
        sections: Optional[list[str]] = None 
        operation: Optional[CsvOperation] = None 
        while True:
            item = await self.channel.queue.get()
            if item is None:
                break
            
            if item["type"] == State.SECTION_NAME:
                item = cast(SectionItem, item) # tell type checker that this is section item
                # if the batch is not empty (previous table data was not all added), add it first
                if len(batch) > 0:
                    if tableName is not None and operation is not None and sections is not None:
                        self._applyDataChange(tableName, operation, sections, batch)
                    else:
                        raise Exception("could not apply change as some values are None")
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

            if len(batch) >= 200:
                if tableName is not None and operation is not None and sections is not None:
                    self._applyDataChange(tableName, operation, sections, batch)
                else:
                    raise Exception("could not apply change as some values are None")
        if batch:
            if tableName is not None and operation is not None and sections is not None:
                self._applyDataChange(tableName, operation, sections, batch)
            else:
                raise Exception("could not apply change as some values are None")
        self.conn.commit()
   
    def _applyDataChange(self, tableName:str, operation: CsvOperation, sections: list[str], batch: list[list]):
        if operation == CsvOperation.UPSERT:
            self._upsert(tableName, sections, batch)
            self.channel.results["rowsUpserted"] += len(batch)
        elif operation == CsvOperation.DELETE:
            self._delete(tableName, sections, batch)
            self.channel.results["rowsDeleted"] += len(batch)
        else:
            raise Exception(f"Unknown operation type: {operation}")
        batch.clear()
    
    def _getTablePrimaries(self, tableName: str) -> list[str]:
        sql = """
            SELECT kcu.column_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
            ON tc.constraint_name = kcu.constraint_name
            AND tc.table_schema = kcu.table_schema
            WHERE tc.constraint_type = 'PRIMARY KEY'
            AND tc.table_name = %s
            AND tc.table_schema = 'public'
            """
        self.cursor.execute(sql, (tableName, ))
        rows = self.cursor.fetchall()
        return [row[0] for row in rows]
    
    def _upsert(self, tableName: str, sections: list[str], values: list[list]):
        try:
            primaries = set(self._getTablePrimaries(tableName))
        except:
            raise Exception(f"Failed to get primary keys for table {tableName}")

        colSet = set(sections)
        isOnlyPrimaries = False
        if colSet == primaries:
            isOnlyPrimaries = True

        if isOnlyPrimaries:
            conflictQuery = f"ON CONFLICT ({', '.join([self._quoteIdent(section) for section in primaries])}) DO NOTHING"
        else:
            conflictQuery = f"ON CONFLICT ({', '.join([self._quoteIdent(section) for section in primaries])}) DO UPDATE SET"
            updateSet = StringIO()
            for section in sections:
                if section not in primaries:
                    updateSet.write(f"{self._quoteIdent(section)} = EXCLUDED.{self._quoteIdent(section)}, ")        
            conflictQuery = f"{conflictQuery} {updateSet.getvalue()[:-2]}"

        try:
            sql = f"insert into {self._quoteIdent(tableName)} ({', '.join([self._quoteIdent(section) for section in sections])}) values %s {conflictQuery}"
            execute_values(self.cursor, sql, values)
        except Exception as e:
            raise Exception(f"row does not match structure: {e}")

    def _delete(self, tableName: str, sections: list[str], values: list[list]):
        whereClauses = [f"{self._quoteIdent(where)} = %s" for where in sections]
        sql = f"DELETE FROM {self._quoteIdent(tableName)} WHERE {' AND '.join(whereClauses)}"
        self.cursor.executemany(sql, values)

    def updateHoldingMetadata(self, holdingId: int, lastSince: Optional[str], nextSince: Optional[str]):
        sql = f"UPDATE \"holding\" SET \"last_since\" = %s, \"next_since\" = %s WHERE \"id\" = %s"
        self.cursor.execute(sql, (lastSince, nextSince, holdingId))
        self.conn.commit()

    def updateFarmMetadata(self, farmId: int, lastSince: Optional[str], nextSince: Optional[str]):
        sql = f"UPDATE \"farm\" SET \"last_since\" = %s, \"next_since\" = %s WHERE \"id\" = %s"
        self.cursor.execute(sql, (lastSince, nextSince, farmId))
        self.conn.commit()

    def _getExistingCols(self,tableName:str) -> list[str]:
        self.cursor.execute(f"SELECT column_name, UPPER(data_type) FROM information_schema.columns WHERE table_name = '{tableName}';")
        try:
            columns = [row[0] for row in self.cursor.fetchall()]
        except Exception as e:
            raise Exception(f"Failed to read columns for {tableName}: {e}")
        return columns
    
    def _addMissingCols(self, table: TableInfo, existing: list[str]) -> int:
        added = 0
        for col in table.columns:
            if col.name not in existing:
                sqlType = Transforms.jdbcToDialect(col.jdbcType, self.dialect)
                try:
                    self.cursor.execute(f"alter table {self._quoteIdent(table.name)} add column {self._quoteIdent(col.name)} {sqlType}")
                    self.conn.commit()
                    print(f'Added col {col.name} to {table.name}')
                    added += 1
                except Exception as e:
                    raise Exception(f"failed to add column {col.name} into {table.name}: {e}")
        return added

    def _tableExists(self,tableName: str) -> bool:
        self.cursor.execute("SELECT COUNT(*) FROM information_schema.tables WHERE table_name = %s", (tableName,))
        results = self.cursor.fetchone() 
        if results is None:
            raise Exception(f"Failed to check if table exists: {tableName}")
        return results[0] > 0

    def _generateTable(self,table: TableInfo) -> None:
        parts = {jdbc.name: Transforms.jdbcToDialect(jdbc.jdbcType, self.dialect) for jdbc in table.columns}
        partString = ", ".join(f"{self._quoteIdent(k)} {v}" for k,v in parts.items())
        primaryString = ""
        if len(table.key) > 0:
            primaryString = f", PRIMARY KEY ({','.join(self._quoteIdent(k) for k in table.key)})"
        self.cursor.execute(f"CREATE TABLE IF NOT EXISTS {self._quoteIdent(table.name)} ({partString}{primaryString})")
        self.conn.commit()
        