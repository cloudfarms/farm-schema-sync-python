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
        if len(buffer) > 0:
            parameters.append(buffer)
        print("", end="")
        return (parameters, not isInQuotes)


if __name__ == "__main__":
    csv = """7946,3356834327,12911008993,,2024-08-02,YL,2,,8993,,,N,F,N,,,,30155C9AB000028007B20C01,,,,,,,,N,,,,,,,,N,3170855275,3170855275,2025-01-27T11:00:00Z,,,,2025-02-20T08:10:09.268717Z,40419,2025-02-20T08:23:27.860529Z,2005181,
7946,3356834329,12911009061,,2024-08-03,YL,2,,9061,,,N,F,N,,,,30155C9AB000028007B20C45,,,,,,,,N,,,,,,,,N,3170855275,3170855275,2025-01-27T11:00:00Z,,,,2025-02-20T08:10:09.268717Z,40419,2025-02-20T08:23:27.860529Z,2005181,
7946,3356834333,12911009075,,2024-08-03,YL,2,,9075,,,N,F,N,,,,30155C9AB000028007B20C53,,,,,,,,N,,,,,,,,N,3170855275,3170855275,2025-01-27T11:00:00Z,,,,2025-02-20T08:10:09.268717Z,40419,2025-02-20T08:23:27.860529Z,2005181,
7946,3377542233,03041032286,,2024-10-05,YL,159,,10322,,,N,F,N,,,3041032286,,,,,,,,,N,2025-08-11,,,,,,,N,1383446798,1383446798,2025-03-04T11:00:00Z,,,,2025-04-04T10:38:44.210378Z,40419,2025-08-26T10:51:38.205996Z,-1,
7946,3377542241,03041031983,,2024-09-16,YL,159,,10319,,,N,F,N,,,"3041031983
",,,,,,,,,N,2025-07-23,,,,,,,N,1383446798,1383446798,2025-03-04T11:00:00Z,,,,2025-04-04T10:38:44.210378Z,40419,2025-08-26T10:51:38.205996Z,-1,
7946,3377542247,03041032003,,2024-09-17,YL,159,,10320,,,N,F,N,,,"3041032003
",,,,,,,,,N,2025-07-24,,,,,,,N,1383446798,1383446798,2025-03-04T11:00:00Z,,,,2025-04-04T10:38:44.210378Z,40419,2025-08-26T10:51:38.205996Z,-1,
"""
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
