from my_app.config import config
from my_app.client import Client
from my_app.database import Database
from my_app.transforms import Transforms

def main():
    client = Client(config)
    client.authenticate()
    tables = client.getAllTables()
    dbClient = Database("something.db")
    dbClient.execSchema(tables)
    holdings = client.getHoldings()

    # flattening hierarchy
    holdingRows = Transforms.flatten_holdings(holdings, None)
    farmRows = Transforms.collectFarms(holdings)

    print(f"Found {len(holdingRows)} holdings and {len(farmRows)} farms")

if __name__ == "__main__":
    main()