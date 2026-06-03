from farmSync.database.queries import SqlGenerator
from farmSync.models import TableInfo, RsColumnInfo
from farmSync.core.enums import Dialect
from typing import Any
from farmSync.core.transforms import Transforms
from io import StringIO


class MsSqlGenerator(SqlGenerator):

    def __init__(self)->None:
        self.dialect = Dialect.MSSQL
        self.placeholder = "?"
        
    def _quoteIdent(self, name: str) -> str:
        escaped = name.replace('[', '[[')
        escaped = escaped.replace(']', ']]')
        return f'[{escaped}]'
    
    def _addPrecision(self, colInfo: RsColumnInfo, sqlType: str):
        if sqlType == "NVARCHAR":
            if colInfo.precision > 1024:
                return "NVARCHAR(MAX) COLLATE SQL_Latin1_General_CP1_CS_AS"
            else:
                return f"NVARCHAR({colInfo.precision}) COLLATE SQL_Latin1_General_CP1_CS_AS"
        if sqlType == "DECIMAL":
            return f"DECIMAL({colInfo.precision},{colInfo.scale})"
        if sqlType == "DATETIME2":
            return "DATETIME2(6)"
        if sqlType == "TIME":
            return "TIME(6)"
        return sqlType

    def getTableExistQuery(self) -> str:
        return ("SELECT 1 FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA = 'dbo'"
            f" AND TABLE_NAME = {self.placeholder}")
    
    def getExistingColsQuery(self,tableName:str) -> tuple[str,tuple[Any, ...], tuple[int,int]]:
        query = ("SELECT COLUMN_NAME, CASE"
        " WHEN DATA_TYPE IN ('varchar', 'char', 'nvarchar', 'nchar', 'varbinary', 'binary') THEN"
        " DATA_TYPE + '(' + CASE WHEN CHARACTER_MAXIMUM_LENGTH = -1 THEN 'max'"
        " ELSE CAST(CHARACTER_MAXIMUM_LENGTH AS VARCHAR(10)) END + ')'"
        " WHEN DATA_TYPE IN ('decimal', 'numeric') THEN DATA_TYPE +"
        " '(' + CAST(NUMERIC_PRECISION AS VARCHAR(10)) + ',' +"
        " CAST(NUMERIC_SCALE AS VARCHAR(10)) + ')'"
        " WHEN DATA_TYPE IN ('datetime2') THEN DATA_TYPE + '(' +"
        " CAST(DATETIME_PRECISION  AS VARCHAR(10)) + ')'"
        " ELSE DATA_TYPE END AS FORMATTED_TYPE FROM INFORMATION_SCHEMA.COLUMNS"
        f" WHERE TABLE_SCHEMA = 'dbo' AND TABLE_NAME = {self.placeholder};")

        return query, (tableName,), (0,1)

    def getAddColQueries(self, table: TableInfo, existing: list[str]) -> list[tuple[str, str]]:
        queries = []
        for col in table.columns:
            if col.name not in existing:
                sqlType = Transforms.jdbcToDialect(col.jdbcType, self.dialect)
                finalType = self._addPrecision(col, sqlType)
                quotedTable = self._quoteIdent(table.name)
                quotedCol = self._quoteIdent(col.name)
                query = f"ALTER TABLE {quotedTable} ADD {quotedCol} {finalType}"
                queries.append((query, col.name))
        return queries
    

    def getNewTableQuery(self, table: TableInfo) -> tuple[str, dict[str, str]]:
        typeCache = {}
        partString = StringIO()
        for col in table.columns:
            sqlType = Transforms.jdbcToDialect(col.jdbcType, self.dialect)
            finalType = self._addPrecision(col, sqlType)

            typeCache[col.name] = finalType
            partString.write(f"{self._quoteIdent(col.name)} {finalType}")
            partString.write(", ")

        pkString = self._getPrimaryKeyString(table.key)
        query = (f"IF OBJECT_ID(N'{self._quoteIdent(table.name)}', N'U') IS NULL CREATE TABLE "
                f"{self._quoteIdent(table.name)} ({partString.getvalue()}{pkString})")
        return query, typeCache
    
    def getHoldingDdl(self):
        return """
            IF OBJECT_ID(N'holding', N'U') IS NULL CREATE TABLE [holding] (
            [id] BIGINT NOT NULL PRIMARY KEY,
            [name] NVARCHAR(MAX),
            [parent_id] BIGINT,
            [external_id] NVARCHAR(MAX),
            [customers_id] NVARCHAR(MAX),
            [internal_name] NVARCHAR(MAX),
            [active] BIT,
            [last_sync] NVARCHAR(MAX),
            [last_since] NVARCHAR(MAX),
            [next_since] NVARCHAR(MAX)
        )
        """

    def getFarmDdl(self):
        return """
            IF OBJECT_ID(N'farm', N'U') IS NULL CREATE TABLE [farm] (
            [id] BIGINT NOT NULL PRIMARY KEY,
            [name] NVARCHAR(MAX),
            [holding_id] BIGINT,
            [farm_type] NVARCHAR(MAX),
            [time_zone] NVARCHAR(MAX),
            [external_id] NVARCHAR(MAX),
            [customers_id] NVARCHAR(MAX),
            [internal_name] NVARCHAR(MAX),
            [last_sync] NVARCHAR(MAX),
            [last_since] NVARCHAR(MAX),
            [next_since] NVARCHAR(MAX)
        )
        """


    def getHoldingInsertQuery(self) -> str:
        return f"""
            MERGE [holding] WITH (HOLDLOCK) AS target
                USING (
                    SELECT
                        {self.placeholder} AS [id],
                        {self.placeholder} AS [name],
                        {self.placeholder} AS [parent_id],
                        {self.placeholder} AS [external_id],
                        {self.placeholder} AS [customers_id],
                        {self.placeholder} AS [internal_name]
                ) AS source
                ON target.[id] = source.[id]

                WHEN MATCHED THEN
                    UPDATE SET
                        target.[name] = source.[name],
                        target.[parent_id] = source.[parent_id],
                        target.[external_id] = source.[external_id],
                        target.[customers_id] = source.[customers_id],
                        target.[internal_name] = source.[internal_name]

                WHEN NOT MATCHED THEN
                    INSERT ([id], [name], [parent_id], [external_id], [customers_id], [internal_name])
                    VALUES (
                        source.[id],
                        source.[name],
                        source.[parent_id],
                        source.[external_id],
                        source.[customers_id],
                        source.[internal_name]
                    );
            """

    def getFarmInsertQuery(self) -> str:
        return f"""
            MERGE [farm] WITH (HOLDLOCK) AS target
                USING (
                    SELECT
                        {self.placeholder} AS [id],
                        {self.placeholder} AS [name],
                        {self.placeholder} AS [holding_id],
                        {self.placeholder} AS [farm_type],
                        {self.placeholder} AS [time_zone],
                        {self.placeholder} AS [external_id],
                        {self.placeholder} AS [customers_id],
                        {self.placeholder} AS [internal_name]
                ) AS source
                ON target.[id] = source.[id]

                WHEN MATCHED THEN
                    UPDATE SET
                        target.[name] = source.[name],
                        target.[holding_id] = source.[holding_id],
                        target.[farm_type] = source.[farm_type],
                        target.[time_zone] = source.[time_zone],
                        target.[external_id] = source.[external_id],
                        target.[customers_id] = source.[customers_id],
                        target.[internal_name] = source.[internal_name]

                WHEN NOT MATCHED THEN
                    INSERT (
                    [id], [name], [holding_id], [farm_type], [time_zone],
                    [external_id], [customers_id], [internal_name]
                    )
                    VALUES (
                        source.[id],
                        source.[name],
                        source.[holding_id],
                        source.[farm_type],
                        source.[time_zone],
                        source.[external_id],
                        source.[customers_id],
                        source.[internal_name]
                    );
                """

    def getHoldingIdsQuery(self)-> str:
        return 'SELECT [id], [next_since] FROM [holding] WHERE [parent_id] IS NULL'

    def getFarmIdsQuery(self) -> str:
        return 'SELECT [id], [next_since] FROM [farm]'

    def getUpdateHoldingMetaQuery(self)-> str:
        return (f"UPDATE [holding] SET [last_since] = {self.placeholder},"
                f" [next_since] = {self.placeholder} WHERE [id] = {self.placeholder}")

    def getUpdateFarmMetaQuery(self)-> str:
        return (f"UPDATE [farm] SET [last_since] = {self.placeholder},"
                f" [next_since] = {self.placeholder} WHERE [id] = {self.placeholder}")
    
    def getTempTableQuery(self, tableName: str, sections: list[str], types: dict[str, str])-> tuple[str, str]:
        stagingTable = f"##temp_{tableName}"
        stagingColsDef = []
        for section in sections:
            colType = types.get(section, "NVARCHAR(MAX)")
            if "nvarchar" in colType.lower():
                colType = f"{colType} COLLATE SQL_Latin1_General_CP1_CS_AS"
            stagingColsDef.append(f"{self._quoteIdent(section)} {colType}")

        return stagingTable, f"CREATE TABLE {self._quoteIdent(stagingTable)} ({', '.join(stagingColsDef)});"
    def getUpsertQuery(self, tableName: str, sections: list[str], primaries: set[str],
                       tempTable: str) -> str:

        nonKeys = [section for section in sections if section not in primaries]

        quotedPrimaries = [self._quoteIdent(section) for section in primaries]
        quotedNonKeys = [self._quoteIdent(section) for section in nonKeys]
        onClause = " AND ".join([f"target.{s} = source.{s}" for s in quotedPrimaries])
        insertCols = ", ".join([self._quoteIdent(s) for s in sections])
        insertVals = ", ".join([f"source.{self._quoteIdent(s)}" for s in sections])
        update_clause = ""
        if nonKeys:
            update_set = ", ".join([f"target.{s} = source.{s}" for s in quotedNonKeys])
            update_clause = f"WHEN MATCHED THEN UPDATE SET {update_set}"

        return f"""
            MERGE {self._quoteIdent(tableName)} WITH (HOLDLOCK) AS target
            USING {tempTable} AS source
            ON {onClause}
            {update_clause}
            WHEN NOT MATCHED THEN
                INSERT ({insertCols})
                VALUES ({insertVals});
        """