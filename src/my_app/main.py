from my_app.config import config
from my_app.client import Client
from my_app.database import Database
from my_app.transforms import Transforms
from my_app.asyncController import AsyncController
from my_app.pipelineChannel import PipelineChannel
import sys
import re
import asyncio

def main():
    asyncio.run(run())

async def run():
    client = Client(config)
    client.authenticate()
    tables = client.getAllTables()
    # argument parsing and verification
    try:
        dbName = sys.argv[1]
        if re.fullmatch(r"\w+\.db", dbName) is None:
            print("Invalid name for database. Database files must end with .db")
            exit(0)
    except:
        dbName = "farmSync.db"
    
    print(f"DATABASE NAME: {dbName}")
    dbClient = Database(dbName)
    results = dbClient.execSchema(tables)

    print("\nSCHEMA SYNC COMPLETE:")
    print(f"---Tables created: {results['tablesCreated']}")
    print(f"---Tables already existing: {results['tablesExisting']}")
    print(f"---Columns added to existing tables: {results['colsAdded']}")
    print(f"---Total tables: {results['tablesCreated'] + results['tablesExisting']}")

    holdings = client.getHoldings()
    # flattening hierarchy
    holdingRows = Transforms.flatten_holdings(holdings, None)
    farmRows = Transforms.collectFarms(holdings)

    print(f"Found {len(holdingRows)} holdings and {len(farmRows)} farms")

    results = dbClient.syncOrgData(holdingRows, farmRows)

    print("\nORGANIZATION SYNC COMPLETE")
    print(f"---Holdings upserted {results['holdingsUpserted']}")
    print(f"---Farms upserted {results['farmsUpserted']}")

    keyMap = Transforms.buildKeyMap(tables)

    holdingIds = dbClient.readHoldingIds()
    farmIds = dbClient.readFarmIds()

    print(f"\nSyncing data changes for {len(holdingIds)} holdings and {len(farmIds)} farms")

    totalUpserted = 0
    totalDeleted = 0
    holdingsProcessed = 0
    farmsProcessed = 0

    for holdingId, nextSince in holdingIds:
        print(f"Holding {holdingId} (since: {nextSince})")
        path = f"/cfapi/holding/{holdingId}/data-changes"
        controller = AsyncController(client, dbClient)
        await controller.run(path, nextSince)

if __name__ == "__main__":
    main()