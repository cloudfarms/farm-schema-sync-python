import sqlite3
from models import TableInfo

class Database:

    def __init__(self,dbName):
        self.conn = sqlite3.connect(dbName)
        self.cursor = self.conn.cursor()
    
    def execSchema(self, tables: list[TableInfo]):
        results = {"tablesCreated": 0, "tablesExisting": 0, "colsAdded": 0}
        for table in tables:
            exists = self.tableExists(table.name)
            if exists:
                existing = self.getExistingCols(table.name)
                added = self.addMissingCols(table, existing)
                if added > 0:
                    print(f"Table {table.name} updated with {added} new cols")
                else:
                    print(f"Table {table.name} is already up to date")
                results["colsAdded"] += added
                results["tablesExisting"] += 1
                continue
            try:
                self.generateTable(table)
                results["tablesCreated"] += 1
            except:
                raise Exception(f"Failed to create table {table.name}")
        return results

    def getExistingCols(self,tableName:str) -> list[str]:
        self.cursor.execute(f"PRAGMA table_info({tableName})")
        try:
            columns = [row[1] for row in self.cursor.fetchall()]
        except:
            raise Exception(f"Failed to read columns for {tableName}")
        return columns
    
    def addMissingCols(self, table: TableInfo, existing: list[str]) -> int:
        added = 0
        for col in table.columns:
            if col.name not in existing:
                sqlType = self.jdbcToSqlite(col.jdbcType)
                try:
                    self.cursor.execute(f"alter table {table.name} add column {col.name} {sqlType}")
                    self.conn.commit()
                    print(f'Added col {col.name} to {table.name}')
                    added += 1
                except:
                    raise Exception(f"failed to add column {col.name} into {table.name}")
        return added

    def tableExists(self,tableName: str):
        self.cursor.execute(f"SELECT 1 FROM sqlite_master WHERE type='table' AND name= ?", (tableName,))
        return self.cursor.fetchone() is not None

    def generateTable(self,table: TableInfo):
        parts = {jdbc.name: self.jdbcToSqlite(jdbc.jdbcType) for jdbc in table.columns}
        partString = ", ".join(f"{k} {v}" for k,v in parts.items())
        primaryString = ""
        if len(table.key) > 0:
            primaryString = f", PRIMARY KEY ({','.join(table.key)})"
        self.cursor.execute(f"CREATE TABLE IF NOT EXISTS {table.name} ({partString}{primaryString})")
        self.conn.commit()
        

    def jdbcToSqlite(self, jdbc:int):
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