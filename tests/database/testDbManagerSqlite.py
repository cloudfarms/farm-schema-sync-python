import unittest
import asyncio
import sqlite3
from farmSync.core.enums.csvOperation import CsvOperation
from farmSync.core.enums.state import State
from farmSync.database.dbManager import DbManager 
from farmSync.models import SqliteDbConfig, TableInfo, RsColumnInfo, HoldingRow, FarmRow
from farmSync.core.enums import Dialect
from farmSync.database.queries import SqliteGenerator

EMPLOYEES_TABLE = TableInfo(
    name="employees",
    key=["id"],
    columns=[
        RsColumnInfo(
            name="id",
            jdbcType=4,          
            dbTypeName="INT",
            scale=0,
            precision=10
        ),
        RsColumnInfo(
            name="first_name",
            jdbcType=12,         
            dbTypeName="VARCHAR",
            scale=0,
            precision=50
        ),
    ]
)

class MockChannel:
    def __init__(self):
        self.queue = asyncio.Queue()
        self.results = {"rowsDeleted": 0, "rowsUpserted": 0}

class TestDbManagerSqlite(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        """Runs before every single test case. Sets up a fresh in-memory DB."""
        self.config = SqliteDbConfig(dbName=":memory:")
        self.mgr = DbManager(self.config, Dialect.SQLITE)
        self.mgr.channel = MockChannel() # type: ignore

    def tearDown(self):
        """Runs after every single test case. Closes and destroys the database."""
        self.mgr.conn.close()

    def testSetUp(self):
        """Tests that the manager has been set up properly"""
        self.assertTrue(self.mgr.conn)
        self.assertTrue(self.mgr.cursor)
        self.assertTrue(self.mgr.generator)

        self.assertEqual(self.mgr.dialect, Dialect.SQLITE)
        self.assertIsInstance(self.mgr.generator, SqliteGenerator)
        self.assertIsInstance(self.mgr.conn, sqlite3.Connection)
        self.assertIsInstance(self.mgr.cursor, sqlite3.Cursor)
    

    def testExecSchema(self):
        """Tests that the schema is created properly.""" 
        results = self.mgr.execSchema([EMPLOYEES_TABLE])

        self.assertEqual(results["colsAdded"], 0)
        self.assertEqual(results["tablesCreated"], 1)
        self.assertEqual(results["tablesExisting"], 0)

        tableExistQuery = ("SELECT name FROM sqlite_master WHERE type='table' AND"
                           f" name='{EMPLOYEES_TABLE.name}'")
        colDataQuery = (f"PRAGMA table_info({EMPLOYEES_TABLE.name})")
        try:
            self.mgr.cursor.execute(tableExistQuery)
            result = self.mgr.cursor.fetchone()
            self.assertEqual(result[0], EMPLOYEES_TABLE.name) # type: ignore
        except Exception as e:
            self.fail(f"Failed to execute table exist test queries: {e}")

        try:
            self.mgr.cursor.execute(colDataQuery)
            result = self.mgr.cursor.fetchall()
            self.assertEqual(len(result), len(EMPLOYEES_TABLE.columns))
        except Exception as e:
            self.fail(f"Failed to execute col information test queries: {e}")

        colNames = [result[1] for result in result] # type: ignore
        expectedNames = [col.name for col in EMPLOYEES_TABLE.columns]
        self.assertEqual(colNames, expectedNames)

    def testExecSchemaNewCol(self):
        """Tests that a new column is added to an existing table."""
        self.mgr.cursor.execute(f"CREATE TABLE {EMPLOYEES_TABLE.name} (id INTEGER PRIMARY KEY)")
        table = EMPLOYEES_TABLE
        results = self.mgr.execSchema([table])

        self.assertEqual(results["colsAdded"], 1)
        self.assertEqual(results["tablesCreated"], 0)
        self.assertEqual(results["tablesExisting"], 1)

        tableExistQuery = ("SELECT name FROM sqlite_master WHERE type='table' AND"
                           f" name='{EMPLOYEES_TABLE.name}'")
        colDataQuery = (f"PRAGMA table_info({EMPLOYEES_TABLE.name})")
        try:
            self.mgr.cursor.execute(tableExistQuery)
            result = self.mgr.cursor.fetchone()
            self.assertEqual(result[0], EMPLOYEES_TABLE.name) # type: ignore
        except Exception as e:
            self.fail(f"Failed to execute table exist test queries: {e}")

        try:
            self.mgr.cursor.execute(colDataQuery)
            result = self.mgr.cursor.fetchall()
            self.assertEqual(len(result), len(EMPLOYEES_TABLE.columns))
        except Exception as e:
            self.fail(f"Failed to execute col information test queries: {e}")

        colNames = [result[1] for result in result] # type: ignore
        expectedNames = [col.name for col in EMPLOYEES_TABLE.columns]
        self.assertEqual(colNames, expectedNames)
    
    def testSyncOrgData(self):
        """Tests that the org data is synced properly."""
        farmA = FarmRow(id=101, name="A", farmType="A", timeZone="A", externalId="E1",
                        customersId="t1", internalName="a", holdingId=1)
        farmB = FarmRow(id=102, name="B", farmType="B", timeZone="B", externalId="E2",
                        customersId="t2", internalName="b", holdingId=2)
        parentHolding = HoldingRow(id=1, name="Parent", externalId="E1", customersId="t2", 
                                   internalName="p", parentId=None)
        subHolding = HoldingRow( id = 2, name = "child", parentId = 1, externalId = "E2",
                                customersId = "t1", internalName = "c")
        holdings = [parentHolding, subHolding]
        farms = [farmA, farmB]

        result = self.mgr.syncOrgData(holdings, farms)
        self.assertEqual(result["holdingsUpserted"], 2)
        self.assertEqual(result["farmsUpserted"], 2)

        try:
            self.mgr.cursor.execute("SELECT COUNT(*) FROM holding;")
            holdingsCount = self.mgr.cursor.fetchone()[0] # type: ignore
            
            self.mgr.cursor.execute("SELECT COUNT(*) FROM farm;")
            farmsCount = self.mgr.cursor.fetchone()[0] # type: ignore
            
            self.mgr.cursor.execute("SELECT name FROM holding WHERE id = 1;")
            holdingRow = self.mgr.cursor.fetchone()

            self.mgr.cursor.execute("SELECT name, holding_id FROM farm WHERE id = 102;")
            farmRow = self.mgr.cursor.fetchone()
            
        except Exception as e:
            self.fail(f"Independent verification queries crashed: {e}")

        self.assertEqual(holdingsCount, 2, "Database missing holding records.")
        self.assertEqual(farmsCount, 2, "Database missing farm records.")

        self.assertIsNotNone(holdingRow, "Holding 1 was not found in the database")
        self.assertEqual(holdingRow[0], parentHolding.name) # type: ignore
        
        self.assertIsNotNone(farmRow, "Farm 102 was not found in the database.")
        self.assertEqual(farmRow[0], farmB.name) # type: ignore
        self.assertEqual(farmRow[1], farmB.holdingId) # type: ignore

    def testSyncOrgDataConflict(self):
        """Tests that data is properly updated in case it exists already."""
        farmA = FarmRow(id=101, name="A", farmType="A", timeZone="A", externalId="E1",
                        customersId="t1", internalName="a", holdingId=1)
        farmB = FarmRow(id=102, name="B", farmType="B", timeZone="B", externalId="E2",
                        customersId="t2", internalName="b", holdingId=2)
        parentHolding = HoldingRow(id=1, name="Parent", externalId="E1", customersId="t2", 
                                   internalName="p", parentId=None)
        subHolding = HoldingRow( id = 2, name = "child", parentId = 1, externalId = "E2",
                                customersId = "t1", internalName = "c")
        holdings = [parentHolding, subHolding]
        farms = [farmA, farmB]

        self.mgr.syncOrgData(holdings, farms)
        parentHoldingUpdated = HoldingRow(id=1, name="UPDATED Parent Name", externalId="E1",
                                          customersId="t2", internalName="p", parentId=None)
        
        farmBUpdated = FarmRow(id=102, name="UPDATED Farm B", farmType="Z", timeZone="B",
                               externalId="E2", customersId="t2", internalName="b", holdingId=2)

        updatedHoldings = [parentHoldingUpdated]
        updatedFarms = [farmBUpdated]
        result = self.mgr.syncOrgData(updatedHoldings, updatedFarms)
        self.assertEqual(result["holdingsUpserted"], 1)
        self.assertEqual(result["farmsUpserted"], 1)

        try:
            self.mgr.cursor.execute("SELECT COUNT(*) FROM holding;")
            holdingsCount = self.mgr.cursor.fetchone()[0] # type: ignore
            
            self.mgr.cursor.execute("SELECT COUNT(*) FROM farm;")
            farmsCount = self.mgr.cursor.fetchone()[0] # type: ignore
            
            self.mgr.cursor.execute("SELECT name FROM holding WHERE id = 1;")
            holdingRow = self.mgr.cursor.fetchone()

            self.mgr.cursor.execute("SELECT name, holding_id FROM farm WHERE id = 102;")
            farmRow = self.mgr.cursor.fetchone()
            
        except Exception as e:
            self.fail(f"Independent verification queries crashed: {e}")

        self.assertEqual(holdingsCount, 2, "Database missing holding records.")
        self.assertEqual(farmsCount, 2, "Database missing farm records.")

        self.assertIsNotNone(holdingRow, "Holding 1 was not found in the database")
        self.assertEqual(holdingRow[0], parentHoldingUpdated.name) # type: ignore
        
        self.assertIsNotNone(farmRow, "Farm 102 was not found in the database.")
        self.assertEqual(farmRow[0], farmBUpdated.name) # type: ignore
        self.assertEqual(farmRow[1], farmBUpdated.holdingId) # type: ignore

    def testReadHoldingIds(self):
        """Tests that readHoldingIds fetch the correct ID collections."""
        try:
            self.mgr.cursor.execute("CREATE TABLE IF NOT EXISTS 'holding'"
                                    " (id INTEGER PRIMARY KEY, name TEXT, parent_id INTEGER,"
                                    " external_id TEXT, customers_id TEXT, internal_name TEXT,"
                                    " active BOOLEAN, last_sync TEXT, last_since TEXT,"
                                    " next_since TEXT);")
            self.mgr.cursor.execute(
                "INSERT INTO holding (id, name, parent_id, external_id, customers_id,"
                " internal_name, next_since) VALUES "
                "(10, 'Holding One', NULL,'EXT-H1', 'cust-1', 'h1', NULL),"
                "(20, 'Holding Two', NULL,'EXT-H2', 'cust-1', 'h2', '2026-05-28T10:50:03.392823Z'),"
                "(30, 'Holding Three', 10,'EXT-H3', 'cust-1', 'h3', NULL);"
            )
            self.mgr.conn.commit()
        except Exception as e:
            self.fail(f"Test setup failed! Could not seed manual data via SQL: {e}")

        holdingData = self.mgr.readHoldingIds()

        expectedHoldingData = [
            (10, None),
            (20, "2026-05-28T10:50:03.392823Z")
        ]

        self.assertEqual(len(holdingData), len(expectedHoldingData))

        self.assertCountEqual(
            holdingData, 
            expectedHoldingData, 
            f"Holding IDs mismatch! Expected {expectedHoldingData}, got {holdingData}"
        )


    def testReadHoldingIdsEmpty(self):
        """Tests that readHoldingIds fetch the correct ID collections."""
        try:
            self.mgr.cursor.execute("CREATE TABLE IF NOT EXISTS 'holding'"
                                    " (id INTEGER PRIMARY KEY, name TEXT, parent_id INTEGER,"
                                    " external_id TEXT, customers_id TEXT, internal_name TEXT,"
                                    " active BOOLEAN, last_sync TEXT, last_since TEXT,"
                                    " next_since TEXT);")
            self.mgr.conn.commit()
        except Exception as e:
            self.fail(f"Test setup failed! Could not seed manual data via SQL: {e}")

        holdingData = self.mgr.readHoldingIds()
        self.assertEqual(len(holdingData), 0)

        self.assertCountEqual(
            holdingData, 
            [], 
            f"Holding IDs mismatch! Got {holdingData}"
        )

    def testReadFarmIds(self):
        """Tests that readHoldingIds fetch the correct ID collections."""
        try:
            self.mgr.cursor.execute("CREATE TABLE IF NOT EXISTS 'farm'"
                                    " (id INTEGER PRIMARY KEY, name TEXT, holding_id INTEGER,"
                                    " farm_type TEXT, time_zone TEXT, external_id TEXT,"
                                    " customers_id TEXT, internal_name TEXT, last_sync TEXT,"
                                    " last_since TEXT, next_since TEXT);")
            self.mgr.cursor.execute(
                "INSERT INTO farm (id, name, holding_id, next_since) VALUES"
                "(10, 'Farm 1', 1, NULL),"
                "(20, 'Farm 2', 2, '2026-05-28T10:50:03.392823Z');" 
            )
            self.mgr.conn.commit()
        except Exception as e:
            self.fail(f"Test setup failed! Could not seed manual data via SQL: {e}")

        farmData = self.mgr.readFarmIds()

        expectedFarmData = [
            (10, None),
            (20, "2026-05-28T10:50:03.392823Z")
        ]

        self.assertEqual(len(farmData), len(expectedFarmData))

        self.assertCountEqual(
            farmData, 
            expectedFarmData, 
            f"Farm IDs mismatch! Expected {expectedFarmData}, got {farmData}"
        )


    def testReadFarmIdsEmpty(self):
        """Tests that readHoldingIds fetch the correct ID collections."""
        try:
            self.mgr.cursor.execute("CREATE TABLE IF NOT EXISTS 'farm'"
                                    " (id INTEGER PRIMARY KEY, name TEXT, holding_id INTEGER,"
                                    " farm_type TEXT, time_zone TEXT, external_id TEXT,"
                                    " customers_id TEXT, internal_name TEXT, last_sync TEXT,"
                                    " last_since TEXT, next_since TEXT);")
            self.mgr.conn.commit()
        except Exception as e:
            self.fail(f"Test setup failed! Could not seed manual data via SQL: {e}")

        farmData = self.mgr.readFarmIds()
        self.assertEqual(len(farmData), 0)

        self.assertCountEqual(
            farmData, 
            [], 
            f"Holding IDs mismatch! Got {farmData}"
        )


    async def testAsyncConsumer(self):
        self.mgr.cursor.execute("CREATE TABLE IF NOT EXISTS users (id INT PRIMARY KEY, name TEXT);")
        self.mgr.cursor.execute("CREATE TABLE IF NOT EXISTS logs (id INT PRIMARY KEY, msg TEXT);")
        self.mgr.conn.commit()
        self.mgr.pkCache["users"] = ["id"]
        self.mgr.pkCache["logs"] = ["id"]

        queue = self.mgr.channel.queue
        await queue.put({"type": State.SECTION_NAME, "table": "users", "operation": CsvOperation.UPSERT})
        await queue.put({"type": State.HEADER, "data": ("id", "name")})
        
        for i in range(5002):
            await queue.put({"type": State.ROWS, "data": (i, f"User_{i}")})

        await queue.put({"type": State.SECTION_NAME, "table": "logs", "operation": CsvOperation.UPSERT})
        await queue.put({"type": State.HEADER, "data": ("id", "msg")})
        await queue.put({"type": State.ROWS, "data": (999, "System Alert")})

        await queue.put(None)

        await self.mgr.applyDataChangesConsumer()

        try:
            # 1. Verify 'users' table got all 5,002 rows (threshold cut + trailing cut)
            self.mgr.cursor.execute("SELECT COUNT(*) FROM users;")
            usersCount = self.mgr.cursor.fetchone()[0] # type: ignore
            self.assertEqual(usersCount, 5002, "Failed to flush complete batch or trailing rows to 'users'.")

            # 2. Verify 'logs' table got its row (proving the state switch flush worked)
            self.mgr.cursor.execute("SELECT COUNT(*) FROM logs;")
            logsCount = self.mgr.cursor.fetchone()[0] # type: ignore
            self.assertEqual(logsCount, 1, "Failed to flush table changes during State.SECTION_NAME transition.")

            # 3. Read specific field data to verify integrity
            self.mgr.cursor.execute("SELECT msg FROM logs WHERE id = 999;")
            logMsg = self.mgr.cursor.fetchone()[0] # type: ignore
            self.assertEqual(logMsg, "System Alert")

        except Exception as e:
            self.fail(f"Database validation query failed or threw an unexpected crash: {e}")