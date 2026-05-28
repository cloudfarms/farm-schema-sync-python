import unittest
from farmSync.database.queries import MsSqlGenerator
from farmSync.models import TableInfo, RsColumnInfo

class TestMsSqlGenerator(unittest.TestCase):

    def setUp(self):
        self.generator = MsSqlGenerator()

    def testGetTableExistsQuery(self):
        """Verify the exact SQLite metadata table selection string layout."""
        query = self.generator.getTableExistQuery()
        expected = ("SELECT 1 FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA = 'dbo'"
            " AND TABLE_NAME = ?")

        self.assertEqual(query, expected, "Query does not match expected format.")

    def testAddPrecisionDecimal(self):
        colInfo = RsColumnInfo(name="id", jdbcType=2, dbTypeName="NUMERIC", scale=5, precision=12)
        sqlType = self.generator._addPrecision(colInfo, "DECIMAL")
        expected = "DECIMAL(12,5)"
        self.assertEqual(sqlType, expected, "Incorrect SQL type provided.")

    def testAddPrecisionVarchar(self):
        colInfo = RsColumnInfo(name="email", jdbcType=23, dbTypeName="TEXT", scale=0, precision=255)
        sqlType = self.generator._addPrecision(colInfo, "NVARCHAR")
        expected = "NVARCHAR(255) COLLATE SQL_Latin1_General_CP1_CS_AS"
        self.assertEqual(sqlType, expected, "Incorrect SQL type provided.")

    def testAddPrecisionText(self):
        colInfo = RsColumnInfo(name="email", jdbcType=23, dbTypeName="TEXT", scale=0, precision=1030)
        sqlType = self.generator._addPrecision(colInfo, "NVARCHAR")
        expected = "NVARCHAR(MAX) COLLATE SQL_Latin1_General_CP1_CS_AS"
        self.assertEqual(sqlType, expected, "Incorrect SQL type provided.")

    def testAddPrecisionDatetime(self):
        colInfo = RsColumnInfo(name="datetime", jdbcType=93, dbTypeName="TEXT", scale=0, precision=255)
        sqlType = self.generator._addPrecision(colInfo, "DATETIME2")
        expected = "DATETIME2(6)"
        self.assertEqual(sqlType, expected, "Incorrect SQL type provided.")
        
    def testAddPrecisionTime(self):
        colInfo = RsColumnInfo(name="email", jdbcType=92, dbTypeName="TEXT", scale=0, precision=255)
        sqlType = self.generator._addPrecision(colInfo, "TIME")
        expected = "TIME(6)"
        self.assertEqual(sqlType, expected, "Incorrect SQL type provided.")

    def testGetAddColQueries(self):
        """Verify it only appends alter statements for missing columns."""
        col1 = RsColumnInfo(name="id", jdbcType=4, dbTypeName="INTEGER", scale=0, precision=0)
        col2 = RsColumnInfo(name="email", jdbcType=12, dbTypeName="VARCHAR", scale=0, precision=255)
        col3 = RsColumnInfo(name="test", jdbcType=2, dbTypeName="FLOAT", scale=5, precision=12)
        table = TableInfo(name="users", columns=[col1, col2, col3], key=["id"])

        existingCols = ["id"]
        queries = self.generator.getAddColQueries(table, existingCols)

        self.assertEqual(len(queries), 2, "Query count is not equal to given queries.")
        
        sql, colName = queries[0]
        self.assertEqual(colName, "email", "Column name does not match the given name.")
        self.assertIn(("ALTER TABLE [users] ADD [email] NVARCHAR(255)"
                       " COLLATE SQL_Latin1_General_CP1_CS_AS"), sql,
                      "Query does not match expected format.")

        sql, colName = queries[1]
        self.assertEqual(colName, "test", "Column name does not match the given name.")
        self.assertIn("ALTER TABLE [users] ADD [test] DECIMAL(12,5)", sql,
                      "Query does not match expected format.")

    def testGetNewTableQuery(self):
        """Verify dynamic generation builds clean type caches and schema definitions."""
        col1 = RsColumnInfo(name="id", jdbcType=4, dbTypeName="INTEGER", scale=0, precision=0)
        col2 = RsColumnInfo(name="username", jdbcType=12, dbTypeName="VARCHAR", scale=0, precision=255)
        table = TableInfo(name="profiles", columns=[col1, col2], key=["id"])

        query, type_cache = self.generator.getNewTableQuery(table)

        self.assertEqual(type_cache["id"], "INT", "Type cache for id is not correct.")
        self.assertEqual(type_cache["username"], "NVARCHAR(255) COLLATE SQL_Latin1_General_CP1_CS_AS",
                         "Type cache for username is not correct.") 

        expectedSql = ("IF OBJECT_ID(N'[profiles]', N'U') IS NULL CREATE TABLE "
                "[profiles] ([id] INT, [username] NVARCHAR(255) COLLATE SQL_Latin1_General_CP1_CS_AS,"
                " PRIMARY KEY ([id]))")
        self.assertEqual(query, expectedSql, "Query does not match expected format.")