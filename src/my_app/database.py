import sqlite3
from my_app.models import TableInfo, HoldingRow, FarmRow
from typing import TypedDict

class _SchemaResults(TypedDict):
        tablesCreated: int
        tablesExisting: int
        colsAdded: int

class _OrgSyncResult(TypedDict):
    holdingsUpserted: int
    farmsUpserted: int

class Database:

    def __init__(self,dbName):
        self.conn = sqlite3.connect(dbName)
        self.cursor = self.conn.cursor()
    
    def execSchema(self, tables: list[TableInfo]) -> _SchemaResults:
        results = {"tablesCreated": 0, "tablesExisting": 0, "colsAdded": 0}
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
            except:
                raise Exception(f"Failed to create table {table.name}")
        return results
    
    def syncOrgData(self,holdingRows: list[HoldingRow], farmRows: list[FarmRow])-> _OrgSyncResult:
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
        except:
            raise Exception(f"Failed to create table holding")
        try:
            self.cursor.execute(FARM_DDL)
        except:
            raise Exception(f"Failed to create table holding")
        
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
                raise Exception(f"Failedd to upsert holding {hold.id}: {e}")
        
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

    def _getExistingCols(self,tableName:str) -> list[str]:
        self.cursor.execute(f"PRAGMA table_info({tableName})")
        try:
            columns = [row[1] for row in self.cursor.fetchall()]
        except:
            raise Exception(f"Failed to read columns for {tableName}")
        return columns
    
    def _addMissingCols(self, table: TableInfo, existing: list[str]) -> int:
        added = 0
        for col in table.columns:
            if col.name not in existing:
                sqlType = self._jdbcToSqlite(col.jdbcType)
                try:
                    self.cursor.execute(f"alter table {self._quote_ident(table.name)} add column {self._quote_ident(col.name)} {sqlType}")
                    self.conn.commit()
                    print(f'Added col {col.name} to {table.name}')
                    added += 1
                except:
                    raise Exception(f"failed to add column {col.name} into {table.name}")
        return added

    def _tableExists(self,tableName: str):
        self.cursor.execute(f"SELECT 1 FROM sqlite_master WHERE type='table' AND name= ?", (tableName,))
        return self.cursor.fetchone() is not None

    def _generateTable(self,table: TableInfo):
        parts = {jdbc.name: self._jdbcToSqlite(jdbc.jdbcType) for jdbc in table.columns}
        partString = ", ".join(f"{self._quote_ident(k)} {v}" for k,v in parts.items())
        primaryString = ""
        if len(table.key) > 0:
            primaryString = f", PRIMARY KEY ({','.join(self._quote_ident(k) for k in table.key)})"
        self.cursor.execute(f"CREATE TABLE IF NOT EXISTS {self._quote_ident(table.name)} ({partString}{primaryString})")
        self.conn.commit()
        
    def _quote_ident(self, name: str) -> str:
        escaped = name.replace('"', '""')
        return f'"{escaped}"'

    def _jdbcToSqlite(self, jdbc:int):
        matchDict = {
                    12: "TEXT",
                    1: "TEXT",
                    -1: "TEXT",
                    -9: "TEXT",
                    -15: "TEXT",
                    -16: "TEXT",
                    -5: "INTEGER",
                    -6:"INTEGER",
                    5:"INTEGER",
                    4: "INTEGER",
                    2:"REAL",
                    3:"REAL",
                    7:"REAL",
                    8:"REAL",
                    6:"REAL",
                    -7:"INTEGER",
                    16:"INTEGER",
                    93:"TEXT",
                    92:"TEXT",
                    91:"TEXT",
                    -4:"BLOB",
                    -3:"BLOB",
                    -2:"BLOB",
                    2004:"BLOB"
                     }
        sqlite = None
        try:
            sqlite = matchDict[jdbc]
        except:
            sqlite = "TEXT"
        return sqlite
