from my_app.models import OrgHolding, HoldingRow, FarmRow, TableInfo
from typing import Optional

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
        buffer = ""
        if isContinue:
            if oldParams is None:
                raise Exception("Old parameter list is empty. It must contain some values")
            buffer = oldParams[-1]
            parameters = oldParams[:-1]

        isInQuotes = isContinue        
        for i, ch in enumerate(line):
            if isInQuotes:
                if ch == "\"":
                    if i+1 >= len(line) or line[i+1] == ",":
                        isInQuotes = False
                else:
                    buffer = buffer + ch
            else:
                if ch == "\"":
                    isInQuotes = True
                elif ch == ",":
                    parameters.append(buffer)
                    buffer = ""
                    if i+1 >= len(line):
                        parameters.append("")
                else:
                    buffer = buffer + ch
        if isInQuotes:
            buffer = buffer + "\n"
        if len(buffer) > 0:
            parameters.append(buffer)
        return (parameters, not isInQuotes)


if __name__ == "__main__":
    csv = """8640,52319217,P06X7285,18035,2020-09-03,Glenn Weaver,,,,,,N,N,N,N,N,N,N,,,,,,,,,,2457675511,2,served,,2022-10-01T15:34:55.859680Z,-1,2025-12-03T12:22:40.452698Z,-1,
8640,52319218,P06X7888,18036,2020-09-12,Glenn Weaver,,,,,,N,N,N,N,N,N,N,,,,,,,,,,2,2,inactive,,2022-10-01T15:34:55.859680Z,-1,2025-12-03T12:22:40.452698Z,-1,
8640,52319219,P06X8498,18037,2020-09-16,Glenn Weaver,,,,"

",,N,N,N,N,N,N,N,,,,,,,,,,2457675511,2,inactive,,2022-10-01T15:34:55.859680Z,-1,2023-04-30T04:52:32.707817Z,-1,"""
    isContinue = False
    oldParams = None
    finished = []
    for line in csv.split("\n"):
        res, isDone = Transforms.parseCsvLine(line, isContinue, oldParams)
        isContinue = not isDone
        if isContinue:
            oldParams = res
        else:
            finished.append(res)
    print("")
    print(finished)
