from farmSync.database.queries import SqlGenerator
from farmSync.models import SchemaResults, FarmRow, HoldingRow, OrgSyncResult
from farmSync.models import TableInfo, SectionItem, SyncItem
from farmSync.core.enums import State, CsvOperation, Dialect
from typing import Optional, cast, Any
from farmSync.models import RsColumnInfo
from farmSync.core.transforms import Transforms
from io import StringIO

class PostgresGenerator(SqlGenerator):

    def __init__(self)->None:
        self.dialect = Dialect.POSTGRES
        self.placeholder = "%s"

    async def applyDataChangesConsumer(self):
        batch = []
        tableName: Optional[str] = None 
        sections: Optional[list[str]] = None 
        operation: Optional[CsvOperation] = None 
        while True:
            item = await self.tableMap.queue.get()
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
        except Exception:
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

    def _quoteIdent(self, name: str) -> str:
        escaped = name.replace('"', '""')
        return f'"{escaped}"'

    def getTableExistQuery(self) -> str:
        return f"SELECT COUNT(*) FROM information_schema.tables WHERE table_name = {self.placeholder}"

    def getExistingColsQuery(self,tableName:str) -> tuple[str,tuple[Any, ...], int]:
        query = ("SELECT column_name, UPPER(data_type)"
        f" FROM information_schema.columns WHERE table_name = {self.placeholder};")
        return query, (tableName,), 0

    def getAddColQueries(self, table: TableInfo, existing: list[str]) -> list[str]:
        queries = []
        for col in table.columns:
            if col.name not in existing:
                sqlType = Transforms.jdbcToDialect(col.jdbcType, self.dialect)
                finalType = self._addPrecision(col, sqlType)
                quotedTable = self._quoteIdent(table.name)
                quotedCol = self._quoteIdent(col.name)
                query = f"ALTER TABLE {quotedTable} ADD COLUMN {quotedCol} {finalType}"
                queries.append((query, col.name))
        return queries

    def _addPrecision(self, colInfo: RsColumnInfo, sqlType: str):
        if sqlType == "NUMERIC":
            return f"NUMERIC({colInfo.precision},{colInfo.scale})"
        return sqlType
    
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
    
    def getFarmDdl(self):
        return """
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
    
    def getHoldingInsertQuery(self) -> str:
        placeholders = [self.placeholder for _ in range(6)]
        return (''        
        'INSERT INTO "holding" ("id", "name", "parent_id", "external_id",'
        ' "customers_id", "internal_name")'
        f' VALUES ({", ".join(placeholders)})'
        ' ON CONFLICT ("id") DO UPDATE SET'
        ' "name" = EXCLUDED."name",'
        ' "parent_id" = EXCLUDED."parent_id",'
        ' "external_id" = EXCLUDED."external_id",'
        ' "customers_id" = EXCLUDED."customers_id",'
        ' "internal_name" = EXCLUDED."internal_name"')

    def getFarmInsertQuery(self) -> str:
        placeholders = [self.placeholder for _ in range(8)]
        return (''
        'INSERT INTO "farm" ("id", "name", "holding_id", "farm_type", "time_zone",'
        ' "external_id", "customers_id", "internal_name")'
        f' VALUES ({", ".join(placeholders)})'
        ' ON CONFLICT (id) DO UPDATE SET'
        ' "name" = EXCLUDED."name",'
        ' "holding_id" = EXCLUDED."holding_id",'
        ' "farm_type" = EXCLUDED."farm_type",'
        ' "time_zone" = EXCLUDED."time_zone",'
        ' "external_id" = EXCLUDED."external_id",'
        ' "customers_id" = EXCLUDED."customers_id",'
        ' "internal_name" = EXCLUDED."internal_name"')

    def getHoldingIdsQuery(self)->str:
        return 'SELECT "id", "next_since" FROM "holding" WHERE "parent_id" IS NULL'

    def getFarmIdsQuery(self) -> str:
        return 'SELECT "id", "next_since" FROM "farm"'