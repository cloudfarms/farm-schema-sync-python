from my_app.models import OrgHolding, HoldingRow, FarmRow, TableInfo

class Transforms:
    """
        Handles other logic, such as transformation of data 
    """
    @staticmethod
    def flatten_holdings(holdings: list[OrgHolding], parentId: int) -> list[HoldingRow]:
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
    def buildKeyMap(tables: list[TableInfo]) -> dict[str, list[str]]:
        keymap = {}
        for table in tables:
            keymap[table.name] = table.key
        
        return keymap