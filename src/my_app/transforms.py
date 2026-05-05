from my_app.models import OrgHolding, HoldingRow, FarmRow
from my_app.enums import Dialect
from my_app.dbMappingTypes import SQLITE_TYPES, POSTGRES_TYPES
from typing import Optional
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
        raise Exception("Unknown dialect")