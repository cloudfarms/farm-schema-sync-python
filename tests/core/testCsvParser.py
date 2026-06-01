import unittest
from unittest.mock import MagicMock
from typing import cast

from farmSync.core.enums import Dialect, State, CsvOperation
from farmSync.core.pipelineChannel import PipelineChannel
from farmSync.models import SectionItem, SyncItem, PythonTableInfo, PythonColumnInfo
from farmSync.core.csvParser import CsvParser
from farmSync.core.transforms import Transforms

class TestCsvParser(unittest.TestCase):

    def setUp(self):
        self.channel = PipelineChannel(Dialect.SQLITE)
        self.parser = CsvParser(self.channel)
        self._originalStrToType = Transforms.strToType
        self._originalParseCsvLine = Transforms.parseCsvLine
        Transforms.strToType = MagicMock(side_effect=lambda val, type_name, dialect: f"typed_{val}")
        Transforms.parseCsvLine = MagicMock(return_value=(["parsed_val"], True))

    def testParseLineNoData(self):
        """Validates empty body fails."""
        with self.assertRaises(Exception) as e:
            self.parser.parseLine(None)
        self.assertEqual(str(e.exception), "Invalid CSV Response: empty body")
    
    def testParseLineIncorrectStart(self):
        """Validates first line is 'data'."""
        with self.assertRaises(Exception) as e:
            self.parser.parseLine("test")
        
        expected = "Invalid CSV Response: expected first line to be \"data\". Got test"
        self.assertEqual(str(e.exception), expected)

    def testParseLineMultiline(self):
        """Validates a complete golden-path multi-line stream lifecycle."""
        # 1. State: START -> expects 'data'
        res = self.parser.parseLine("data")
        self.assertIsNone(res)
        self.assertEqual(self.parser.state, State.METADATA_HEADER)

        # 2. State: METADATA_HEADER -> assigns header metadata to channel
        res = self.parser.parseLine("meta_col1,meta_col2")
        self.assertIsNone(res)
        self.assertEqual(self.channel.updateHeader, ["meta_col1", "meta_col2"])
        self.assertEqual(self.parser.state, State.METADATA_ROW)

        # 3. State: METADATA_ROW -> assigns values metadata to channel
        res = self.parser.parseLine("val1,val2")
        self.assertIsNone(res)
        self.assertEqual(self.channel.updateRow, ["val1", "val2"])
        self.assertEqual(self.parser.state, State.WAIT)

        # 4. State: SECTION_NAME -> assigns table name and operation
        res = self.parser.parseLine("products_upserted")
        self.assertIsNotNone(res)
        res = cast(SectionItem, res)
        self.assertEqual(res["type"], State.SECTION_NAME)
        self.assertEqual(res["table"], "products")
        self.assertEqual(res["operation"], CsvOperation.UPSERT)
        self.assertEqual(self.parser.state, State.HEADER)

        # 5. State: HEADER -> extracts columns definitions 
        res = self.parser.parseLine("sku,price")
        self.assertIsNotNone(res)
        res = cast(SyncItem, res)
        self.assertEqual(res["type"], State.HEADER)
        self.assertEqual(res["data"], ("sku", "price"))
        self.assertEqual(self.parser.state, State.ROWS)

        # 6. State: ROWS -> extracts row payload data
        res = self.parser.parseLine("SKU001,19.99")
        self.assertIsNotNone(res)
        res = cast(SyncItem, res)
        self.assertEqual(res["type"], State.ROWS)
        self.assertEqual(res["data"], ("parsed_val",))
    

    def testParseEmptyLines(self):
        """Verifies empty strings and * asterisks return None and don't trip states."""
        self.parser.state = State.WAIT
        
        self.assertIsNone(self.parser.parseLine(""))
        self.assertIsNone(self.parser.parseLine("   "))
        self.assertIsNone(self.parser.parseLine("*"))
        self.assertEqual(self.parser.state, State.WAIT)
    
    def testParseLineMultipleLineBuffer(self):
        """Tests that incomplete quoted rows are held in a buffer until finished."""
        self.parser.state = State.ROWS
        
        Transforms.parseCsvLine = MagicMock(return_value=(["partial_data"], False))
        res = self.parser.parseLine('"unclosed_quote_data')
        
        self.assertIsNone(res)
        self.assertEqual(self.parser.buffer, ["partial_data"])

        Transforms.parseCsvLine = MagicMock(return_value=(["partial_data", "completed"], True))
        res2 = self.parser.parseLine('closed_quote_data"')

        self.assertIsNotNone(res2)
        res2 = cast(SyncItem, res2)
        self.assertEqual(res2["type"], State.ROWS)
        self.assertEqual(res2["data"], ("partial_data", "completed"))
        self.assertIsNone(self.parser.buffer)


    def testTranslateToPython(self):
        """Verifies raw string rows convert values into typed data casting schemas."""
        cols = [
            PythonColumnInfo(name="sku", typeName=str),
            PythonColumnInfo(name="quantity", typeName=int),
        ]
        inventory = PythonTableInfo(name="inventory", columns={"sku": cols[0],
                                                               "quantity": cols[1]}, key=[])
        tableMap = {"inventory": inventory}
        
        self.parser.cols = ["sku", "quantity"]
        self.parser.translation = tableMap["inventory"]

        inputRow = SyncItem({"type": State.ROWS, "data": ("SKU-ALPHA", "500")})
        output = self.parser.translateToPython(inputRow, tableMap)
        output = cast(SyncItem, output)
        self.assertEqual(output["data"], ("typed_SKU-ALPHA", "typed_500"))

    def tearDown(self):
        Transforms.strToType = self._originalStrToType
        Transforms.parseCsvLine = self._originalParseCsvLine
