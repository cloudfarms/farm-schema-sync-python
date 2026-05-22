from farmSync.config import loadConfig, loadDbConfig
from farmSync.core.enums import Dialect
from farmSync.client import Client
from farmSync.database import DbManager
from farmSync.core.transforms import Transforms
from farmSync.core.asyncController import AsyncController
from farmSync.models import ServerDbConfig, SqliteDbConfig
import argparse
import sys
import re
import asyncio
import time

def main():
    asyncio.run(run())

async def run():
    
    startTime = time.time()
    parser = argparse.ArgumentParser() 
    parser.add_argument("-db", "--dbName", help="Name of database file to use",
                        nargs="?", default="farmSync.db")
    parser.add_argument("-d", "--dialect", help="Database dialect to use", 
                        choices=["sqlite", "mysql", "postgres", "mssql"], default="sqlite")

    args = parser.parse_args()
    try:
        dbName = args.dbName
    except Exception:
        dbName = "farmSync.db"

    if re.fullmatch(r"\w+\.db", dbName) is None:
        print("Invalid name for database. Database files must end with .db")
        sys.exit(1)

    dialect = Dialect(args.dialect)
    print(f"SELECTED DIALECT: {dialect}")
    if dialect == Dialect.SQLITE:
        print(f"DATABASE NAME: {dbName}")
        dbConfig = SqliteDbConfig.model_validate({"dbName": dbName})
    else:
        dbConfig = ServerDbConfig.model_validate(loadDbConfig().__dict__)
        print(f'DATABASE NAME: {dbConfig.dbName}')

    config = loadConfig()
    client = Client(config)
    client.authenticate()
    tables = client.getAllTables()
    # table map allows for quicker parsing later
    tableMap = Transforms.getTableMap(tables)
    dbClient = DbManager(dbConfig, dialect)
    results = dbClient.execSchema(tables)

    print("\nSCHEMA SYNC COMPLETE:")
    print(f"---Tables created: {results['tablesCreated']}")
    print(f"---Tables already existing: {results['tablesExisting']}")
    print(f"---Columns added to existing tables: {results['colsAdded']}")
    print(f"---Total tables: {results['tablesCreated'] + results['tablesExisting']}")

    holdings = client.getHoldings()
    holdingRows = Transforms.flatten_holdings(holdings, None)
    farmRows = Transforms.collectFarms(holdings)

    print(f"Found {len(holdingRows)} holdings and {len(farmRows)} farms")

    results = dbClient.syncOrgData(holdingRows, farmRows)

    print("\nORGANIZATION SYNC COMPLETE")
    print(f"---Holdings upserted {results['holdingsUpserted']}")
    print(f"---Farms upserted {results['farmsUpserted']}")

    holdingIds = dbClient.readHoldingIds()
    farmIds = dbClient.readFarmIds()

    print(f"\nSyncing data changes for {len(holdingIds)} holdings and {len(farmIds)} farms")

    raise Exception("test")
    totalUpserted = 0
    totalDeleted = 0
    holdingsProcessed = 0
    farmsProcessed = 0
    lastTimestamp = time.time()
    for holdingId, since in holdingIds:
        print(f"Holding {holdingId} (since: {since})...", end="")
        path = f"/cfapi/holding/{holdingId}/data-changes"
        controller = AsyncController(client, dbClient, tableMap)
        await controller.run(path, since)

        results = controller.channel.results
        totalUpserted += results['rowsUpserted']
        totalDeleted += results['rowsDeleted']
        holdingsProcessed += 1
        print(f"{results['rowsUpserted']} upserted, {results['rowsDeleted']} deleted.",
              f"Took {time.time() - lastTimestamp:.2f}s")
        lastTimestamp = time.time()
        try:
            lastSinceIndex = controller.channel.updateHeader.index("requestedSince")
            lastSince = controller.channel.updateRow[lastSinceIndex]
        except (ValueError, IndexError):
            lastSince = None

        try:
            nextSinceIndex = controller.channel.updateHeader.index("nextSince")
            nextSince = controller.channel.updateRow[nextSinceIndex]
        except (ValueError, IndexError):
            nextSince = None

        dbClient.updateHoldingMetadata(holdingId, lastSince, nextSince)

    for farmId, since in farmIds:
        print(f"Farm {farmId} (since: {since})...", end="")
        path = f"/cfapi/farm/{farmId}/data-changes"
        controller = AsyncController(client, dbClient, tableMap)
        await controller.run(path, since)

        results = controller.channel.results
        totalUpserted += results['rowsUpserted']
        totalDeleted += results['rowsDeleted']
        farmsProcessed += 1

        print(f"{results['rowsUpserted']} upserted, {results['rowsDeleted']} deleted.",
              f"Took {time.time() - lastTimestamp:.2f}s")
        lastTimestamp = time.time()
        try:
            lastSinceIndex = controller.channel.updateHeader.index("requestedSince")
            lastSince = controller.channel.updateRow[lastSinceIndex]
        except (ValueError, IndexError):
            lastSince = None

        try:
            nextSinceIndex = controller.channel.updateHeader.index("nextSince")
            nextSince = controller.channel.updateRow[nextSinceIndex]
        except (ValueError, IndexError):
            nextSince = None
        dbClient.updateFarmMetadata(farmId, lastSince, nextSince)

    print("\nDATA SYNC COMPLETE:")
    print(f"---Holdings processed: {holdingsProcessed}")
    print(f"---Farms processed: {farmsProcessed}")
    print(f"---Total rows upserted: {totalUpserted}")
    print(f"---Total rows deleted: {totalDeleted}")
    print(f"---Took {time.time() - startTime:.2f} seconds")

if __name__ == "__main__":
    main()