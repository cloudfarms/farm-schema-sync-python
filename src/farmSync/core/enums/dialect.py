from enum import Enum

class Dialect(str,Enum):
    SQLITE = "sqlite"
    MYSQL = "mysql"
    POSTGRES = "postgres"
    MSSQL = "mssql"