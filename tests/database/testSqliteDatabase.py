import unittest
from farmSync.database.queries import SqliteGenerator
from farmSync.models import TableInfo, RsColumnInfo, SqliteDbConfig
from farmSync.core.enums import Dialect

class TestSqliteDatabaseQueries(unittest.TestCase):

    def setUp(self):
        dummyConfig = SqliteDbConfig(dbName=":memory:") 
        self.db = SqliteGenerator(dummyConfig)

    def testGetTableExistsQuery(self):
        """Verify the exact SQLite metadata table selection string layout."""
        query = self.db.getTableExistQuery()
        expected = f"SELECT 1 FROM sqlite_master WHERE type='table' AND name= ?"
        self.assertEqual(query, expected, "Query does not match expected format.")

    def testGetAddColQueries(self):
        """Verify it only appends alter statements for missing columns."""
        col1 = RsColumnInfo(name="id", jdbcType=4, dbTypeName="INTEGER", scale=0, precision=0)
        col2 = RsColumnInfo(name="email", jdbcType=12, dbTypeName="VARCHAR", scale=0, precision=255)
        col3 = RsColumnInfo(name="test", jdbcType=12, dbTypeName="VARCHAR", scale=0, precision=255)
        table = TableInfo(name="users", columns=[col1, col2, col3], key=["id"])

        existingCols = ["id"]
        queries = self.db.getAddColQueries(table, existingCols)

        self.assertEqual(len(queries), 2, "Query count is not equal to given queries.")
        
        sql, colName = queries[0]
        self.assertEqual(colName, "email", "Column name does not match the given name.")
        self.assertIn("ALTER TABLE \"users\" ADD COLUMN \"email\" TEXT", sql,
                      "Query does not match expected format.")

        sql, colName = queries[1]
        self.assertEqual(colName, "test", "Column name does not match the given name.")
        self.assertIn("ALTER TABLE \"users\" ADD COLUMN \"test\" TEXT", sql,
                      "Query does not match expected format.")

    def testGetNewTableQuery(self):
        """Verify dynamic generation builds clean type caches and schema definitions."""
        col1 = RsColumnInfo(name="id", jdbcType=4, dbTypeName="INTEGER", scale=0, precision=0)
        col2 = RsColumnInfo(name="username", jdbcType=12, dbTypeName="VARCHAR", scale=0, precision=255)
        table = TableInfo(name="profiles", columns=[col1, col2], key=["id"])

        query, type_cache = self.db.getNewTableQuery(table)

        self.assertEqual(type_cache["id"], "INTEGER", "Type cache for id is not correct.")
        self.assertEqual(type_cache["username"], "TEXT", "Type cache for username is not correct.") 

        expected_sql = "CREATE TABLE IF NOT EXISTS \"profiles\" (\"id\" INTEGER, \"username\" TEXT, PRIMARY KEY (\"id\"))"
        self.assertEqual(query, expected_sql, "Query does not match expected format.")