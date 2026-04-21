from my_app.config import config
from my_app.client import Client
from my_app.database import Database

def main():
    client = Client(config)
    client.authenticate()
    tables = client.getAllTables()
    dbClient = Database("something.db")
    dbClient.execSchema(tables)
    holdings = client.getHoldings()