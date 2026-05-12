from my_app.db import *
from my_app.models import ServerDbConfig, SqliteDbConfig
from my_app.enums import Dialect
from typing import Union, cast

class DbFactory:
    def createDb(self, config: Union[ServerDbConfig, SqliteDbConfig], dialect: Dialect)-> BaseDatabase:
        if dialect == Dialect.SQLITE:
            config = cast(SqliteDbConfig, config)
            return SqliteDatabase(config)
        if dialect == Dialect.POSTGRES:
            config = cast(ServerDbConfig, config)
            return PostgresDatabase(config)
        if dialect == Dialect.MYSQL:
            config = cast(ServerDbConfig, config)
            return MySqlDatabase(config)
        raise Exception("Unknown dialect")