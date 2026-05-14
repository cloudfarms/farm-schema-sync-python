from my_app.db import SqliteDatabase, PostgresDatabase, MySqlDatabase, MssqlDatabase, Database
from my_app.models import ServerDbConfig, SqliteDbConfig
from my_app.enums import Dialect
from typing import Union, cast

class DbFactory:
    def createDb(self, config: Union[ServerDbConfig, SqliteDbConfig], dialect: Dialect)-> Database:
        if dialect == Dialect.SQLITE:
            config = cast(SqliteDbConfig, config)
            return SqliteDatabase(config)
        if dialect == Dialect.POSTGRES:
            config = cast(ServerDbConfig, config)
            return PostgresDatabase(config)
        if dialect == Dialect.MYSQL:
            config = cast(ServerDbConfig, config)
            return MySqlDatabase(config)
        if dialect == Dialect.MSSQL:
            config = cast(ServerDbConfig, config)
            return MssqlDatabase(config)
        raise Exception("Unknown dialect")