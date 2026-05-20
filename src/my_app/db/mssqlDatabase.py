from my_app.db import Database
import mssql_python
from my_app.models import ServerDbConfig, SchemaResults, FarmRow, HoldingRow, OrgSyncResult
from my_app.models import TableInfo, SectionItem, SyncItem, RsColumnInfo
from my_app.enums import State, CsvOperation, Dialect
from typing import Optional, cast
from my_app.transforms import Transforms
from io import StringIO


class MssqlDatabase(Database[ServerDbConfig]):

    def __init__(self,config:ServerDbConfig)->None:
        server = f"Server={config.dbHost},{config.dbPort};"
        database = f"Database={config.dbName};"
        authentication = f"UID={config.dbUser};PWD={config.dbPassword};"
        settings = "TrustServerCertificate=yes;"
        connectionString = server + database + authentication + settings
        self.conn = mssql_python.connect(connectionString)
        self.dialect = Dialect.MSSQL
        self.cursor = self.conn.cursor()
        self.placeholder = "?"
        # caching for later
        self.pkCache = {}
        self.typeCache = {}


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
                self.conn.rollback()
                raise Exception(f"Failed to create table {table.name}: {e}")
        return results

    def _mergeHoldingSql(self) -> str:
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
    
    def _mergeFarmSql(self) -> str:
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

    def syncOrgData(self,holdingRows: list[HoldingRow], farmRows: list[FarmRow])-> OrgSyncResult:
        HOLDING_DDL = """
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
        FARM_DDL = """
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
        
        holdingsUpserted = 0
        for hold in holdingRows:
            try:
                self.cursor.execute(self._mergeHoldingSql(), (hold.id, hold.name, hold.parentId,
                                                              hold.externalId, hold.customersId,
                                                              hold.internalName))
                holdingsUpserted += 1
            except Exception as e:
                self.conn.rollback()
                raise Exception(f"Failed to upsert holding {hold.id}: {e}")
        
        farmsUpserted = 0
        for farm in farmRows:
            try:
                self.cursor.execute(self._mergeFarmSql(), (farm.id, farm.name, farm.holdingId,
                                                           farm.farmType, farm.timeZone,
                                                           farm.externalId, farm.customersId,
                                                           farm.internalName))
                farmsUpserted+=1
            except Exception as e:
                self.conn.rollback()
                raise Exception(f"Failed to upsert farm {farm.id}: {e}")
        self.conn.commit()
        return {"holdingsUpserted": holdingsUpserted, "farmsUpserted": farmsUpserted}

    def readHoldingIds(self)-> list[tuple[int, Optional[str]]]:
        try:
            self.cursor.execute('SELECT [id], [next_since] FROM [holding] WHERE [parent_id] IS NULL')
            rows = self.cursor.fetchall()
            return rows # type: ignore
        except Exception as e:
            self.conn.rollback()
            raise Exception(f"Failed to collect holding IDs: {e}")

    def readFarmIds(self) -> list[tuple[int, Optional[str]]]:
        try:
            self.cursor.execute('SELECT [id], [next_since] FROM [farm]')
            rows = self.cursor.fetchall()
            return rows # type: ignore
        except Exception as e:
            self.conn.rollback()
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
                item = cast(SectionItem, item) 
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
        sql = f"""
            SELECT COLUMN_NAME
            FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS tc
            JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE kcu
                ON tc.CONSTRAINT_NAME = kcu.CONSTRAINT_NAME
            WHERE tc.TABLE_NAME = {self.placeholder}
            AND tc.CONSTRAINT_TYPE = 'PRIMARY KEY'
            ORDER BY kcu.ORDINAL_POSITION;
            """
        self.cursor.execute(sql, (tableName, ))
        rows = self.cursor.fetchall()
        return [row[0] for row in rows] # type: ignore

    def _upsert(self, tableName: str, sections: list[str], values: list[list]):
        try:
            primaries, types = self._get_cached_metadata(tableName)
        except Exception as e:
            self.conn.rollback()
            raise Exception(f"Failed to get cached data for table {tableName}: {e}")

        nonKeys = [section for section in sections if section not in primaries]

        stagingTable = f"##temp_{tableName}"
        stagingColsDef = []
        for section in sections:
            colType = types.get(section, "NVARCHAR(MAX)")
            if "nvarchar" in colType.lower():
                colType = f"{colType} COLLATE SQL_Latin1_General_CP1_CS_AS"
            stagingColsDef.append(f"{self._quoteIdent(section)} {colType}")

        createStagingSql = f"CREATE TABLE {self._quoteIdent(stagingTable)} ({', '.join(stagingColsDef)});"

        onClause = " AND ".join([f"target.{self._quoteIdent(s)} = source.{self._quoteIdent(s)}" for s in primaries])
        insertCols = ", ".join([self._quoteIdent(s) for s in sections])
        insertVals = ", ".join([f"source.{self._quoteIdent(s)}" for s in sections])
        
        update_clause = ""
        if nonKeys:
            update_set = ", ".join([f"target.{self._quoteIdent(s)} = source.{self._quoteIdent(s)}" for s in nonKeys])
            update_clause = f"WHEN MATCHED THEN UPDATE SET {update_set}"

        mergeSql = f"""
            MERGE {self._quoteIdent(tableName)} WITH (HOLDLOCK) AS target
            USING {stagingTable} AS source
            ON {onClause}
            {update_clause}
            WHEN NOT MATCHED THEN
                INSERT ({insertCols})
                VALUES ({insertVals});
        """
        try:
            self.cursor.execute(createStagingSql)
            self.conn.commit() # bulkcopy creates a new connection and needs to see the temporary table
            self.cursor.bulkcopy(stagingTable, values, table_lock=True, batch_size=5000, timeout=120)
            self.cursor.execute(mergeSql)
            self.cursor.execute(f"DROP TABLE {self._quoteIdent(stagingTable)}")
        except Exception as e:
            self.conn.rollback()
            self.cursor.execute(f"IF OBJECT_ID('tempdb..{stagingTable}') IS NOT NULL DROP TABLE {self._quoteIdent(stagingTable)}")
            self.conn.commit()
            raise Exception(f"Issue in table {tableName}: {e}")

    def _get_cached_metadata(self, tableName: str):
        """Helper to fetch and cache column types and primary keys once."""
        if tableName not in self.pkCache:
            self.pkCache[tableName] = set(self._getTablePrimaries(tableName))
        if tableName not in self.typeCache:    
            self.typeCache[tableName] = {}
            self.cursor.execute(f"""
                SELECT COLUMN_NAME, DATA_TYPE, NUMERIC_PRECISION, CHARACTER_MAXIMUM_LENGTH,
                NUMERIC_SCALE, DATETIME_PRECISION
                FROM INFORMATION_SCHEMA.COLUMNS 
                WHERE TABLE_NAME = {self.placeholder}
            """, (tableName,))
            results = self.cursor.fetchall()
            for row in results:
                col = row[0]
                type = row[1]
                if type == "datetime2":
                    type = f"{type}({row[5]})" 
                if type == "nvarchar":
                    if row[3] < 0:
                        type = f"{type}(MAX)"
                    else:
                        type = f"{type}({row[3]})"
                if type == "decimal":
                    type = f"{type}({row[2]},{row[4]})"
                
                self.typeCache[tableName][col] = type
            
        return self.pkCache[tableName], self.typeCache[tableName]

    def _delete(self, tableName: str, sections: list[str], values: list[list]):
        whereClauses = [f"{self._quoteIdent(where)} = {self.placeholder}" for where in sections]
        sql = f"DELETE FROM {self._quoteIdent(tableName)} WHERE {' AND '.join(whereClauses)}"
        self.cursor.executemany(sql, values) # type: ignore

    def updateHoldingMetadata(self, holdingId: int, lastSince: Optional[str], nextSince: Optional[str]):
        sql = f"UPDATE [holding] SET [last_since] = {self.placeholder}, [next_since] = {self.placeholder} WHERE [id] = {self.placeholder}"
        self.cursor.execute(sql, (lastSince, nextSince, holdingId))
        self.conn.commit()

    def updateFarmMetadata(self, farmId: int, lastSince: Optional[str], nextSince: Optional[str]):
        sql = f"UPDATE [farm] SET [last_since] = {self.placeholder}, [next_since] = {self.placeholder} WHERE [id] = {self.placeholder}"
        self.cursor.execute(sql, (lastSince, nextSince, farmId))
        self.conn.commit()

    def _getExistingCols(self,tableName:str) -> list[str]:
        colQuery = f"""
                    SELECT COLUMN_NAME
                    FROM INFORMATION_SCHEMA.COLUMNS
                    WHERE TABLE_SCHEMA = 'dbo'
                    AND TABLE_NAME = {self.placeholder}
                    """
        self.cursor.execute(colQuery, (tableName, ))
        try:
            columns = [row[0] for row in self.cursor.fetchall()] # type: ignore
        except Exception as e:
            self.conn.rollback()
            raise Exception(f"Failed to read columns for {tableName}: {e}")
        return cast(list[str], columns)
    
    def _addMissingCols(self, table: TableInfo, existing: list[str]) -> int:
        added = 0
        for col in table.columns:
            if col.name not in existing:
                sqlType = Transforms.jdbcToDialect(col.jdbcType, self.dialect)
                try:
                    finalType = self._addPrecision(col, sqlType) 
                    if sqlType == "NVARCHAR":
                        finalType = f"{finalType} COLLATE SQL_Latin1_General_CP1_CS_AS"
                    self.cursor.execute(f"alter table {self._quoteIdent(table.name)} add {self._quoteIdent(col.name)} {finalType}")
                    self.conn.commit()
                    print(f'Added col {col.name} to {table.name}')
                    self.typeCache[table.name][col.name] = finalType
                    added += 1
                except Exception as e:
                    self.conn.rollback()
                    raise Exception(f"failed to add column {col.name} into {table.name}: {e}")
        return added

    def _tableExists(self,tableName: str) -> bool:
        existQuery = f"""
                    SELECT 1
                    FROM INFORMATION_SCHEMA.TABLES
                    WHERE TABLE_SCHEMA = 'dbo'
                    AND TABLE_NAME = {self.placeholder}
                    """
        self.cursor.execute(existQuery, (tableName,))
        return self.cursor.fetchone() is not None

    def _generateTable(self,table: TableInfo) -> None:
        pkCache = table.key
        typeCache = {}
        parts = {}
        for jdbc in table.columns:
            parts[jdbc.name] = (Transforms.jdbcToDialect(jdbc.jdbcType, self.dialect), jdbc)

        partString = StringIO()
        for col, info in parts.items():
            type, jdbc = info
            precision = self._addPrecision(jdbc, type)
            typeCache[col] = precision
            partString.write(f"{self._quoteIdent(col)}")
            partString.write(f" {precision}")
            if type == "NVARCHAR":
                partString.write(" COLLATE SQL_Latin1_General_CP1_CS_AS")
            partString.write(", ")

        primaryString = ""
        if len(table.key) > 0:
            primaryString = f"PRIMARY KEY ({','.join(self._quoteIdent(k) for k in table.key)})"
        self.cursor.execute(f"IF OBJECT_ID(N'{table.name}', N'U') IS NULL CREATE TABLE {self._quoteIdent(table.name)} ({partString.getvalue()}{primaryString})")
        self.conn.commit()

        self.pkCache[table.name] = pkCache
        self.typeCache[table.name] = typeCache
        
    def _quoteIdent(self, name: str) -> str:
        escaped = name.replace('[', '[[')
        escaped = escaped.replace(']', ']]')
        return f'[{escaped}]'
    
    def _addPrecision(self, colInfo: RsColumnInfo, sqlType: str):
        if sqlType == "NVARCHAR":
            if colInfo.precision > 254:
                return "NVARCHAR(MAX)"
            else:
                return f"NVARCHAR({colInfo.precision})"
        if sqlType == "DECIMAL":
            return f"DECIMAL({colInfo.precision},{colInfo.scale})"
        if sqlType == "DATETIME2":
            return "DATETIME2(6)"
        if sqlType == "TIME":
            return "TIME(6)"
        return sqlType