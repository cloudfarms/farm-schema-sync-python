from farmSync.database.queries import SqlGenerator
from farmSync.models import TableInfo
from farmSync.core.enums import Dialect
from typing import Any
from farmSync.models import RsColumnInfo
from farmSync.core.transforms import Transforms
from io import StringIO

class PostgresGenerator(SqlGenerator):

    def __init__(self)->None:
        self.dialect = Dialect.POSTGRES
        self.placeholder = "%s"

    def _quoteIdent(self, name: str) -> str:
        escaped = name.replace('"', '""')
        return f'"{escaped}"'

    def getTableExistQuery(self) -> str:
        return f"SELECT COUNT(*) FROM information_schema.tables WHERE table_name = {self.placeholder}"

    def getExistingColsQuery(self,tableName:str) -> tuple[str,tuple[Any, ...], tuple[int,int]]:
        query = ("SELECT column_name, CASE"
        " WHEN data_type IN ('numeric') THEN data_type || '(' || CAST(numeric_precision AS text) ||"
        " ',' || CAST(numeric_scale AS text) || ')'"
        " when data_type like 'timestamp%%' then 'timestamp'"
        " ELSE data_type END AS formatted_type FROM information_schema.columns"
        f" WHERE table_name = {self.placeholder};")
        return query, (tableName,), (0,1)

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
            finalType = self._addPrecision(col, sqlType)
            typeCache[col.name] = sqlType
            partString.write(f"{self._quoteIdent(col.name)} {finalType}")
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

    def getUpdateHoldingMetaQuery(self)-> str:
        return (f"UPDATE \"holding\" SET \"last_since\" = {self.placeholder},"
                f" \"next_since\" = {self.placeholder} WHERE \"id\" = {self.placeholder}")

    def getUpdateFarmMetaQuery(self)-> str:
        return (f"UPDATE \"farm\" SET \"last_since\" = {self.placeholder},"
                f"\"next_since\" = {self.placeholder} WHERE \"id\" = {self.placeholder}")
            
    def getUpsertQuery(self, tableName: str, sections: list[str], primaries: set[str])-> str:
        colSet = set(sections)
        isOnlyPrimaries = colSet == primaries

        quotedPrimaries = [self._quoteIdent(section) for section in primaries]
        if isOnlyPrimaries:
            conflictQuery = f"ON CONFLICT ({', '.join(quotedPrimaries)}) DO NOTHING"
        else:
            conflictQuery = f"ON CONFLICT ({', '.join(quotedPrimaries)}) DO UPDATE SET"
            updateSet = StringIO()
            for section in sections:
                if section not in primaries:
                    quotedSection = self._quoteIdent(section)
                    updateSet.write(f"{quotedSection} = EXCLUDED.{quotedSection}, ")        
            conflictQuery = f"{conflictQuery} {updateSet.getvalue()[:-2]}"

        quotedTable = self._quoteIdent(tableName)
        quotedSections = ', '.join([self._quoteIdent(section) for section in sections])
        return f"INSERT INTO {quotedTable} ({quotedSections}) VALUES {self.placeholder} {conflictQuery}"

    def getDeleteQuery(self, tableName: str, sections: list[str])-> str:
        whereClauses = [f"{self._quoteIdent(where)} = {self.placeholder}" for where in sections]
        return f"DELETE FROM {self._quoteIdent(tableName)} WHERE {' AND '.join(whereClauses)}"