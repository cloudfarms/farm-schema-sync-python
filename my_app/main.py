from config import config
from client import Client
from database import Database

client = Client(config)
client.authenticate()
tables = client.getAllTables()
dbClient = Database("something.db")
dbClient.execSchema(tables)