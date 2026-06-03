import unittest
from datetime import datetime

from farmSync.models import OrgHolding, OrgFarm
from farmSync.core.enums import Dialect
from farmSync.core.transforms import Transforms


class TestTransforms(unittest.TestCase):
    def testFlattenHoldings(self):
        """Verifies deep parent-child holding trees are unwound into a flat array."""


        subHolding = OrgHolding.model_validate({
            "id": 2, "name": "Child Holding", "externalId": "E2", 
            "customersId": "t1", "internalName": "child", "subholdings": None, "farms": None
        })
        parentHolding = OrgHolding.model_validate({
            "id": 1, "name": "Parent Holding", "externalId": "E1", 
            "customersId": "t2", "internalName": "parent", 
            "subholdings": [subHolding], "farms": None
        })

        flatRows = Transforms.flattenHoldings([parentHolding], parentId=None)

        self.assertEqual(len(flatRows), 2)
        self.assertIsNone(flatRows[0].parentId)
        self.assertEqual(flatRows[1].id, 2)
        self.assertEqual(flatRows[1].parentId, 1)

    def testCollectFarms(self):
        """Verifies farms are pooled from all layers of a holding hierarchy."""

        farmA = OrgFarm(id=101, name="A", farmType="A", timeZone="A", externalId="E1",
                        customersId="t1", internalName="a")
        farmB = OrgFarm(id=102, name="B", farmType="B", timeZone="B", externalId="E2",
                        customersId="t2", internalName="b")

        subHolding = OrgHolding.model_validate({
            "id": 2, "name": "Child", "externalId": "E2", "customersId": "t1", 
            "internalName": "c", "subholdings": None, "farms": [farmB]
        })
        parentHolding = OrgHolding.model_validate({
            "id": 1, "name": "Parent", "externalId": "E1", "customersId": "t2", 
            "internalName": "p", "subholdings": [subHolding], "farms": [farmA]
        })

        farms = Transforms.collectFarms([parentHolding])
        self.assertEqual(len(farms), 2)
        self.assertEqual(farms[0].id, 101)  
        self.assertEqual(farms[0].holdingId, 1)
        self.assertEqual(farms[1].id, 102) 
        self.assertEqual(farms[1].holdingId, 2)

    def testParseCsvLineStandard(self):
        """Validates simple unquoted single-line parsing strings resolve immediately."""
        params, isDone = Transforms.parseCsvLine("1,Value,True", isContinue=False, oldParams=None)
        self.assertTrue(isDone)
        self.assertEqual(params, ["1", "Value", "True"])

    def testParseCsvLineMultiline(self):
        """Ensures text blocks severed by newline quotation markers buffer correctly."""
        # Step 1: Pass initial fragment with open quotes
        params, isDone = Transforms.parseCsvLine('1,"This description spans',
                                                 isContinue=False, oldParams=None)
        self.assertFalse(isDone)
        self.assertEqual(params, ["1", "This description spans\n"])

        # Step 2: Feed back into engine along with saved parameter cache
        finalParams, finalDone = Transforms.parseCsvLine('multiple lines",Active',
                                                         isContinue=True, oldParams=params)
        self.assertTrue(finalDone)
        self.assertEqual(finalParams, ["1", "This description spans\nmultiple lines", "Active"])

    def testParseCsvLineCorrupted(self):
        """Verifies that attempting a line continuation without cache triggers an error."""
        with self.assertRaises(Exception):
            Transforms.parseCsvLine("some text", isContinue=True, oldParams=None)


    def testStrToTypeEmpty(self):
        """Empty fields must consistently scale down to type None."""
        self.assertIsNone(Transforms.strToType("", int, Dialect.POSTGRES))
        self.assertIsNone(Transforms.strToType("", str, Dialect.MYSQL))

    def testStrToTypeBool(self):
        """Asserts explicit token handling patterns yield strict boolean assignments."""
        self.assertFalse(Transforms.strToType("n", bool, Dialect.POSTGRES))
        self.assertFalse(Transforms.strToType("N", bool, Dialect.SQLITE))
        self.assertTrue(Transforms.strToType("y", bool, Dialect.POSTGRES))
        self.assertTrue(Transforms.strToType("anything_else", bool, Dialect.POSTGRES))

    def testStrToTypeDatetime(self):
        """Ensures ISO strings drop T/Z text markers exclusively when executing on MySQL."""
        rawISO = "2026-05-28T17:00:00Z"
        
        mysqlRes = Transforms.strToType(rawISO, datetime, Dialect.MYSQL)
        self.assertEqual(mysqlRes, "2026-05-28 17:00:00")

        postgresRes = Transforms.strToType(rawISO, datetime, Dialect.POSTGRES)
        self.assertEqual(postgresRes, rawISO)

    def testStrToTypePrimitive(self):
        """Checks clean primitive assignments for native type definitions."""
        self.assertEqual(Transforms.strToType("15", int, Dialect.SQLITE), 15)
        self.assertEqual(Transforms.strToType("19.99", float, Dialect.SQLITE), 19.99)
        self.assertEqual(Transforms.strToType("data", bytes, Dialect.SQLITE), b"data")


    def testJdbcToDialect(self):
        """Ensures fallback values catch unspecified type tokens uniformly."""
        self.assertEqual(Transforms.jdbcToDialect(4, Dialect.SQLITE), "INTEGER")
        self.assertEqual(Transforms.jdbcToDialect(-999, Dialect.POSTGRES), "TEXT")
        self.assertEqual(Transforms.jdbcToDialect(-999, Dialect.MSSQL), "NVARCHAR(MAX)")

    def testUnknownDialectRaises(self):
        """Verifies unknown dialect definitions crash cleanly instead of leaking memory."""
        with self.assertRaisesRegex(Exception, "Unknown dialect"):
            Transforms.jdbcToDialect(4, "INVALID_DIALECT_ENUM") # type: ignore
