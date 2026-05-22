from io import StringIO
from farmSync.database.queries import SqlGenerator
from farmSync.models import FarmRow, HoldingRow, OrgSyncResult
from farmSync.models import TableInfo, SectionItem, SyncItem
from farmSync.core.enums import State, CsvOperation, Dialect
from typing import Optional, cast, Any
from farmSync.core.transforms import Transforms


class SqliteGenerator(SqlGenerator):

    def __init__(self)->None:
        self.dialect = Dialect.SQLITE
        self.placeholder = '?'

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

    def getTableExistQuery(self) -> str:
        return f"SELECT 1 FROM sqlite_master WHERE type='table' AND name= {self.placeholder}"
    
    def getExistingColsQuery(self,tableName:str) -> tuple[str,tuple[Any, ...], int]:
        return f"PRAGMA table_info({self._quoteIdent(tableName)})", (), 1
    
    def getAddColQueries(self, table: TableInfo, existing: list[str]) -> list[tuple[str,str]]:
        queries = []
        for col in table.columns:
            if col.name not in existing:
                sqlType = Transforms.jdbcToDialect(col.jdbcType, self.dialect)
                quotedTable = self._quoteIdent(table.name)
                quotedCol = self._quoteIdent(col.name)
                query = f"ALTER TABLE {quotedTable} ADD COLUMN {quotedCol} {sqlType}"
                queries.append((query, col.name))
        return queries
    
    def getNewTableQuery(self, table: TableInfo) -> tuple[str, dict[str, str]]:
        typeCache = {}
        partString = StringIO()
        for col in table.columns:
            sqlType = Transforms.jdbcToDialect(col.jdbcType, self.dialect)

            typeCache[col.name] = sqlType
            partString.write(f"{self._quoteIdent(col.name)} {sqlType}")
            partString.write(", ")
        primaryString = self._getPrimaryKeyString(table.key)
        query = (f"CREATE TABLE IF NOT EXISTS {self._quoteIdent(table.name)} "
                 f"({partString.getvalue()}{primaryString})")
        return query, typeCache
    
    def getHoldingDdl(self):
        return """
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
    
    def getFarmDdl(self):
        return """
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
    
    def getHoldingInsertQuery(self) -> str:
        placeholders = [self.placeholder for _ in range(6)]
        return (''
        'INSERT INTO "holding" ("id", "name", "parent_id", "external_id",'
        ' "customers_id", "internal_name")'
        f' VALUES ({', '.join(placeholders)})'
        ' ON CONFLICT ("id") DO UPDATE SET'
        ' "name" = excluded.name,'
        ' "parent_id" = excluded.parent_id,'
        ' "external_id" = excluded.external_id,'
        ' "customers_id" = excluded.customers_id,'
        ' "internal_name" = excluded.internal_name')


    def getFarmInsertQuery(self) -> str:
        placeholders = [self.placeholder for _ in range(8)]
        return (''
            'INSERT INTO "farm" ("id", "name", "holding_id", "farm_type", "time_zone",'
            ' "external_id", "customers_id", "internal_name")'
            f' VALUES ({', '.join(placeholders)})'
            ' ON CONFLICT (id) DO UPDATE SET'
            ' "name" = excluded."name",'
            ' "holding_id" = excluded."holding_id",'
            ' "farm_type" = excluded."farm_type",'
            ' "time_zone" = excluded."time_zone",'
            ' "external_id" = excluded."external_id",'
            ' "customers_id" = excluded."customers_id",'
            ' "internal_name" = excluded."internal_name"')
    
    def getHoldingIdsQuery(self)-> str:
        return 'SELECT "id", "next_since" FROM "holding" WHERE "parent_id" IS NULL'

    def getFarmIdsQuery(self) -> str:
        return 'SELECT "id", "next_since" FROM "farm"'