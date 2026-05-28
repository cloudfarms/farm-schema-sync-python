from io import StringIO
from farmSync.database.queries import SqlGenerator
from farmSync.models import TableInfo
from farmSync.core.enums import Dialect
from typing import Any
from farmSync.core.transforms import Transforms


class SqliteGenerator(SqlGenerator):

    def __init__(self)->None:
        self.dialect = Dialect.SQLITE
        self.placeholder = '?'
    
    def getTableExistQuery(self) -> str:
        return f"SELECT 1 FROM sqlite_master WHERE type='table' AND name= {self.placeholder}"
    
    def getExistingColsQuery(self,tableName:str) -> tuple[str,tuple[Any, ...], tuple[int,int]]:
        return f"PRAGMA table_info({self._quoteIdent(tableName)})", (), (1,2)
    
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

    def getUpdateHoldingMetaQuery(self)-> str:
        return (f"UPDATE \"holding\" SET \"last_since\" = {self.placeholder},"
                f" \"next_since\" = {self.placeholder} WHERE \"id\" = {self.placeholder}")

    def getUpdateFarmMetaQuery(self)-> str:
        return (f"UPDATE \"farm\" SET \"last_since\" = {self.placeholder},"
                f" \"next_since\" = {self.placeholder} WHERE \"id\" = {self.placeholder}")
    
    def getUpsertQuery(self, tableName: str, sections: list[str])-> str:
        quoted_tableName = self._quoteIdent(tableName)
        cols_str = ", ".join([self._quoteIdent(s) for s in sections])
        placeholders = ", ".join(["?"] * len(sections))
        
        return f"INSERT OR REPLACE INTO {quoted_tableName} ({cols_str}) VALUES ({placeholders})"

    def getDeleteQuery(self, tableName: str, sections: list[str])-> str:
        whereClauses = [f"{self._quoteIdent(where)} = {self.placeholder}" for where in sections]
        return f"DELETE FROM {self._quoteIdent(tableName)} WHERE {' AND '.join(whereClauses)}"