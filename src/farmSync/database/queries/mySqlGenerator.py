from farmSync.database.queries import SqlGenerator
from farmSync.models import TableInfo, RsColumnInfo
from farmSync.core.enums import Dialect
from typing import Any
from farmSync.core.transforms import Transforms
from io import StringIO


class MySqlGenerator(SqlGenerator):

    def __init__(self)->None:
        self.dialect = Dialect.MYSQL
        self.placeholder = "%s"
    
    def _quoteIdent(self, name: str) -> str:
        escaped = name.replace('`', '``')
        return f'`{escaped}`'
    
    def _addPrecision(self, col: RsColumnInfo, sqlType: str):
        if sqlType == "VARCHAR":
            if col.precision > 1024:
                return "TEXT"
            else:
                return f"VARCHAR({col.precision})"
        if sqlType == "DECIMAL":
            return f"DECIMAL({col.precision},{col.scale})"
        if sqlType == "DATETIME":
            return "DATETIME(6)"
        if sqlType == "TIME":
            return "TIME(6)"
        return sqlType

    def getTableExistQuery(self) -> str:
        return f"SHOW TABLES LIKE {self.placeholder}"

    def getExistingColsQuery(self,tableName:str) -> tuple[str,tuple[Any, ...], tuple[int,int]]:
        return f"DESCRIBE {self._quoteIdent(tableName)}",(), (0,1)

    def getAddColQueries(self, table: TableInfo, existing: list[str]) -> list[tuple[str, str]]:
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

    def getNewTableQuery(self, table: TableInfo) -> tuple[str, dict[str, str]]:
        typeCache = {}
        partString = StringIO()
        for col in table.columns:
            sqlType = Transforms.jdbcToDialect(col.jdbcType, self.dialect)
            finalType = self._addPrecision(col, sqlType)

            typeCache[col.name] = finalType
            partString.write(f"{self._quoteIdent(col.name)} {finalType}")
            partString.write(", ")
        primaryString = self._getPrimaryKeyString(table.key)
        query = (f"CREATE TABLE IF NOT EXISTS {self._quoteIdent(table.name)} "
                 f"({partString.getvalue()}{primaryString});")
        return query, typeCache

    def getHoldingDdl(self):
        return """
            CREATE TABLE IF NOT EXISTS `holding` (
            `id` BIGINT PRIMARY KEY,
            `name` TEXT,
            `parent_id` BIGINT,
            `external_id` TEXT,
            `customers_id` TEXT,
            `internal_name` TEXT,
            `active` BOOLEAN,
            `last_sync` TEXT,
            `last_since` TEXT,
            `next_since` TEXT
        )
        """
    
    def getFarmDdl(self):
        return """
            CREATE TABLE IF NOT EXISTS `farm` (
            `id` BIGINT PRIMARY KEY,
            `name` TEXT,
            `holding_id` BIGINT,
            `farm_type` TEXT,
            `time_zone` TEXT,
            `external_id` TEXT,
            `customers_id` TEXT,
            `internal_name` TEXT,
            `last_sync` TEXT,
            `last_since` TEXT,
            `next_since` TEXT
        )
        """
    
    def getHoldingInsertQuery(self) -> str:
        placeholders = [self.placeholder for _ in range(6)]
        return (''
        'INSERT INTO `holding` (`id`, `name`, `parent_id`, `external_id`, `customers_id`,'
        ' `internal_name`)'
        f' VALUES ({", ".join(placeholders)})'
        ' ON DUPLICATE KEY UPDATE'
        ' `name` = VALUES(`name`),'
        ' `parent_id` = VALUES(`parent_id`),'
        ' `external_id` = VALUES(`external_id`),'
        ' `customers_id` = VALUES(`customers_id`),'
        ' `internal_name` = VALUES(`internal_name`)')

    def getFarmInsertQuery(self) -> str:
        placeholders = [self.placeholder for _ in range(8)]
        return (''
        'INSERT INTO `farm` (`id`, `name`, `holding_id`, `farm_type`, `time_zone`,'
        ' `external_id`, `customers_id`, `internal_name`)'
        f' VALUES ({", ".join(placeholders)})'
        ' ON DUPLICATE KEY UPDATE'                   
        ' `name` = VALUES(`name`),'                  
        ' `holding_id` = VALUES(`holding_id`),'      
        ' `farm_type` = VALUES(`farm_type`),'        
        ' `time_zone` = VALUES(`time_zone`),'        
        ' `external_id` = VALUES(`external_id`),'    
        ' `customers_id` = VALUES(`customers_id`),'  
        ' `internal_name` = VALUES(`internal_name`)')
    

    def getHoldingIdsQuery(self)-> str:
        return 'SELECT `id`, `next_since` FROM `holding` WHERE `parent_id` IS NULL'

    def getFarmIdsQuery(self) -> str:
        return 'SELECT `id`, `next_since` FROM `farm`'

    def getUpdateHoldingMetaQuery(self)->str:
        return (f"UPDATE `holding` SET `last_since` = {self.placeholder},"
                f" `next_since` = {self.placeholder} WHERE `id` = {self.placeholder}")

    def getUpdateFarmMetaQuery(self)->str:
        return (f"UPDATE `farm` SET `last_since` = {self.placeholder},"
                f" `next_since` = {self.placeholder} WHERE `id` = {self.placeholder}")
    
    def getUpsertQuery(self, tableName: str, sections: list[str], primaries: set[str])-> str:
        colSet = set(sections)
        isOnlyPrimaries = colSet == primaries

        quotedTable = self._quoteIdent(tableName)
        quotedSections = [self._quoteIdent(section) for section in sections]
        joinedSections = ', '.join(quotedSections)
        placeholders = ', '.join([self.placeholder] * len(sections))
        if isOnlyPrimaries:
            return f"INSERT IGNORE INTO {quotedTable} ({joinedSections}) VALUES ({placeholders})"
        else:
            insertSql = f"INSERT INTO {quotedTable} ({joinedSections}) VALUES ({placeholders})"
            updateSections = ', '.join([f'{section} = VALUES({section})' for section in quotedSections])
            updateSql = f"ON DUPLICATE KEY UPDATE {updateSections}"
            return f"{insertSql} {updateSql}"

    def getDeleteQuery(self, tableName: str, sections: list[str])-> str:
        whereClauses = [f"{self._quoteIdent(where)} = {self.placeholder}" for where in sections]
        return f"DELETE FROM {self._quoteIdent(tableName)} WHERE {' AND '.join(whereClauses)}"