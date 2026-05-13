from my_app.config import loadConfig, loadDbConfig
from my_app.enums import Dialect
from my_app.client import Client
from my_app.db import DbFactory
from my_app.transforms import Transforms
from my_app.asyncController import AsyncController
from my_app.models import ServerDbConfig, SqliteDbConfig
import argparse
import sys
import re
import asyncio
import time

def main():
    asyncio.run(run())

async def run():
    startTime = time.time()
    # argument parsing and verification
    parser = argparse.ArgumentParser() 
    parser.add_argument("-db", "--dbName", help="Name of database file to use", nargs="?", default="farmSync.db")
    parser.add_argument("-d", "--dialect", help="Database dialect to use", choices=["sqlite", "mysql", "postgres", "mssql"], default="sqlite")

    args = parser.parse_args()
    try:
        dbName = args.dbName
        if re.fullmatch(r"\w+\.db", dbName) is None:
            print("Invalid name for database. Database files must end with .db")
            sys.exit(1)
    except Exception:
        dbName = "farmSync.db"

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
    # create table map
    tableMap = Transforms.getTableMap(tables)
    dbClient = DbFactory().createDb(dbConfig, dialect)
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

    holdingIds = dbClient.readHoldingIds()
    farmIds = dbClient.readFarmIds()

    print(f"\nSyncing data changes for {len(holdingIds)} holdings and {len(farmIds)} farms")

    totalUpserted = 0
    totalDeleted = 0
    holdingsProcessed = 0
    farmsProcessed = 0

    for holdingId, since in holdingIds:
        print(f"Holding {holdingId} (since: {since})...", end="")
        path = f"/cfapi/holding/{holdingId}/data-changes"
        controller = AsyncController(client, dbClient, tableMap)
        await controller.run(path, since)

        results = controller.channel.results
        totalUpserted += results['rowsUpserted']
        totalDeleted += results['rowsDeleted']
        holdingsProcessed += 1
        print(f"{results['rowsUpserted']} upserted, {results['rowsDeleted']} deleted")
        try:
            lastSinceIndex = controller.channel.updateHeader.index("requestedSince")
            lastSince = controller.channel.updateRow[lastSinceIndex]
        except:
            lastSince = None

        try:
            nextSinceIndex = controller.channel.updateHeader.index("nextSince")
            nextSince = controller.channel.updateRow[nextSinceIndex]
        except:
            nextSince = None
        # update metadata for next time the app is run
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

        print(f"{results['rowsUpserted']} upserted, {results['rowsDeleted']} deleted")
        try:
            lastSinceIndex = controller.channel.updateHeader.index("requestedSince")
            lastSince = controller.channel.updateRow[lastSinceIndex]
        except:
            lastSince = None

        try:
            nextSinceIndex = controller.channel.updateHeader.index("nextSince")
            nextSince = controller.channel.updateRow[nextSinceIndex]
        except:
            nextSince = None
        # update metadata for next time the app is run
        dbClient.updateFarmMetadata(farmId, lastSince, nextSince)

    print("\nDATA SYNC COMPLETE:")
    print(f"---Holdings processed: {holdingsProcessed}")
    print(f"---Farms processed: {farmsProcessed}")
    print(f"---Total rows upserted: {totalUpserted}")
    print(f"---Total rows deleted: {totalDeleted}")
    print(f"---Took {time.time() - startTime} seconds")

if __name__ == "__main__":
    main()