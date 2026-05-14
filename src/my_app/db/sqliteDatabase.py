from my_app.db import Database
import sqlite3
from my_app.models import SqliteDbConfig, SchemaResults, FarmRow, HoldingRow, OrgSyncResult
from my_app.models import TableInfo, SectionItem, SyncItem
from my_app.enums import State, CsvOperation, Dialect
from typing import Optional, cast
from my_app.transforms import Transforms


class SqliteDatabase(Database[SqliteDbConfig]):

    def __init__(self,config:SqliteDbConfig)->None:
        self.conn = sqlite3.connect(config.dbName)
        self.dialect = Dialect.SQLITE
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
            "id" INTEGER PRIMARY KEY,
            "name" TEXT,
            "parent_id" INTEGER,
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
            "id" INTEGER PRIMARY KEY,
            "name" TEXT,
            "holding_id" INTEGER,
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
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT ("id") DO UPDATE SET
                    "name" = excluded.name,
                    "parent_id" = excluded.parent_id,
                    "external_id" = excluded.external_id,
                    "customers_id" = excluded.customers_id,
                    "internal_name" = excluded.internal_name
                                    """, (hold.id, hold.name, hold.parentId, hold.externalId, hold.customersId, hold.internalName))
                holdingsUpserted += 1
            except Exception as e:
                raise Exception(f"Failed to upsert holding {hold.id}: {e}")
        
        farmsUpserted = 0
        for farm in farmRows:
            try:
                self.cursor.execute("""
                    INSERT INTO "farm" ("id", "name", "holding_id", "farm_type", "time_zone", "external_id", "customers_id", "internal_name")
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT (id) DO UPDATE SET
                    "name" = excluded."name",
                    "holding_id" = excluded."holding_id",
                    "farm_type" = excluded."farm_type",
                    "time_zone" = excluded."time_zone",
                    "external_id" = excluded."external_id",
                    "customers_id" = excluded."customers_id",
                    "internal_name" = excluded."internal_name"
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
            self.cursor.execute('select "id", "next_since" from "farm"')
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
    
    def _upsert(self, tableName: str, sections: list[str], values: list[list]):
        try:
            sql = f"insert or replace into {self._quoteIdent(tableName)} ({', '.join([self._quoteIdent(section) for section in sections])}) values ({', '.join(['?'] * len(sections))})"
            self.cursor.executemany(sql, values)
        except Exception as e:
            raise Exception(f"row does not match structure: {e}")

    def _delete(self, tableName: str, sections: list[str], values: list[list]):
        whereClauses = [f"{self._quoteIdent(where)} = ?" for where in sections]
        sql = f"DELETE FROM {self._quoteIdent(tableName)} WHERE {' AND '.join(whereClauses)}"
        self.cursor.executemany(sql, values)

    def updateHoldingMetadata(self, holdingId: int, lastSince: Optional[str], nextSince: Optional[str]):
        sql = f"UPDATE \"holding\" SET \"last_since\" = ?, \"next_since\" = ? WHERE \"id\" = ?"
        self.cursor.execute(sql, (lastSince, nextSince, holdingId))
        self.conn.commit()

    def updateFarmMetadata(self, farmId: int, lastSince: Optional[str], nextSince: Optional[str]):
        sql = f"UPDATE \"farm\" SET \"last_since\" = ?, \"next_since\" = ? WHERE \"id\" = ?"
        self.cursor.execute(sql, (lastSince, nextSince, farmId))
        self.conn.commit()

    def _getExistingCols(self,tableName:str) -> list[str]:
        self.cursor.execute(f"PRAGMA table_info({tableName})")
        try:
            columns = [row[1] for row in self.cursor.fetchall()]
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
        self.cursor.execute(f"SELECT 1 FROM sqlite_master WHERE type='table' AND name= ?", (tableName,))
        return self.cursor.fetchone() is not None

    def _generateTable(self,table: TableInfo) -> None:
        parts = {jdbc.name: Transforms.jdbcToDialect(jdbc.jdbcType, self.dialect) for jdbc in table.columns}
        partString = ", ".join(f"{self._quoteIdent(k)} {v}" for k,v in parts.items())
        primaryString = ""
        if len(table.key) > 0:
            primaryString = f", PRIMARY KEY ({','.join(self._quoteIdent(k) for k in table.key)})"
        self.cursor.execute(f"CREATE TABLE IF NOT EXISTS {self._quoteIdent(table.name)} ({partString}{primaryString})")
        self.conn.commit()
        