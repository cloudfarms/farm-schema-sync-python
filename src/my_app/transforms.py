from my_app.models import OrgHolding, HoldingRow, FarmRow, TableInfo, PythonColumnInfo, PythonTableInfo
from my_app.enums import Dialect
from my_app.dbMappingTypes import *
from typing import Optional, Any
from io import StringIO

class Transforms:
    """
        Handles other logic, such as transformation of data 
    """
    @staticmethod
    def flatten_holdings(holdings: list[OrgHolding], parentId: Optional[int]) -> list[HoldingRow]:
        rows = []
        for holding in holdings:
            row = HoldingRow.model_validate({"id": holding.id, "name": holding.name, "parentId": parentId,
                                       "externalId": holding.externalId, "customersId": holding.customersId,
                                       "internalName": holding.internalName})
            rows.append(row)
            if holding.subholdings is not None:
                rows.extend(Transforms.flatten_holdings(holding.subholdings, holding.id))
        return rows
    
    @staticmethod
    def collectFarms(holdings: list[OrgHolding]) -> list[FarmRow]:
        rows = []
        for holding in holdings:
            if holding.farms is not None:
                for farm in holding.farms:
                    row = FarmRow.model_validate({"id": farm.id, "name": farm.name, "holdingId": holding.id,
                                                  "farmType": farm.farmType, "timeZone": farm.timeZone, "externalId": farm.externalId,
                                                  "customersId": farm.customersId, "internalName": farm.internalName})
                    rows.append(row)
            if holding.subholdings is not None:
                rows.extend(Transforms.collectFarms(holding.subholdings))
        return rows

    @staticmethod
    def parseCsvLine(line: str, isContinue: bool, oldParams: Optional[list[str]])-> tuple[list[str], bool]:
        """
            Due to some csv records being spread among more lines, we need to handle them properly 
        """
        parameters = []
        buffer = StringIO()
        if isContinue:
            if oldParams is None:
                raise Exception("Old parameter list is empty. It must contain some values")
            buffer.write(oldParams[-1])
            parameters = oldParams[:-1]

        isInQuotes = isContinue        
        for i, ch in enumerate(line):
            if isInQuotes:
                if ch == "\"":
                    if i+1 >= len(line) or line[i+1] == ",":
                        isInQuotes = False
                else:
                    buffer.write(ch)
            else:
                if ch == "\"":
                    isInQuotes = True
                elif ch == ",":
                    parameters.append(buffer.getvalue())
                    buffer.seek(0)
                    buffer.truncate(0)
                    if i+1 >= len(line):
                        parameters.append("")
                else:
                    buffer.write(ch)
        if isInQuotes:
            buffer.write("\n")
        if len(buffer.getvalue()) > 0:
            parameters.append(buffer.getvalue())
        return (parameters, not isInQuotes)

    @staticmethod
    def jdbcToDialect(jdbc: int, dialect: Dialect) -> str:
        if dialect == Dialect.SQLITE:
            return SQLITE_TYPES.get(jdbc, "TEXT")
        if dialect == Dialect.POSTGRES:
            return POSTGRES_TYPES.get(jdbc, "TEXT")
        if dialect == Dialect.MYSQL:
            return MYSQL_TYPES.get(jdbc, "TEXT")
        raise Exception("Unknown dialect")
    
    @staticmethod
    def jdbcToPython(jdbc: int) -> type:
        return PYTHON_TYPES.get(jdbc, str)
    
    @staticmethod
    def getTableMap(tables: list[TableInfo]):
        finalTables = {}
        for table in tables:
            cols = []
            for col in table.columns:
                colType = Transforms.jdbcToPython(col.jdbcType)
                cols.append(PythonColumnInfo(name=col.name, typeName=colType))
            finalTables[table.name] = PythonTableInfo(name=table.name, columns=cols, key=table.key)
        return finalTables

    @staticmethod
    def strToType(col: str, type: type)-> Any:
        if col == "":
            return None
        if type == str:
            return col
        if type == int:
            return int(col)
        if type == float:
            return float(col)
        if type == bool:
            if col.lower() == "n":
                return False
            return True
        if type == bytes:
            return col.encode('utf-8')

        return col