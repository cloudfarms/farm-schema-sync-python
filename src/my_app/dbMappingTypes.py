from datetime import time, datetime

SQLITE_TYPES = {
            12: "TEXT",
            1: "TEXT",
            -1: "TEXT",
            -9: "TEXT",
            -15: "TEXT",
            -16: "TEXT",
            -5: "INTEGER",
            -6:"INTEGER",
            5:"INTEGER",
            4: "INTEGER",
            2:"REAL",
            3:"REAL",
            7:"REAL",
            8:"REAL",
            6:"REAL",
            -7:"INTEGER",
            16:"INTEGER",
            93:"TEXT",
            92:"TEXT",
            91:"TEXT",
            -4:"BLOB",
            -3:"BLOB",
            -2:"BLOB",
            2004:"BLOB"
                }

POSTGRES_TYPES = {
    12: "TEXT",
    1: "TEXT", 
    -1: "TEXT",
    -9: "TEXT",
    -15: "TEXT",
    -16: "TEXT",
    -5: "BIGINT",
    -6: "SMALLINT",
    5: "SMALLINT",
    4: "INTEGER",
    2: "NUMERIC",
    3: "NUMERIC",
    7: "REAL",
    8: "DOUBLE PRECISION",
    6: "FLOAT8",
    -7: "BOOLEAN",
    16: "BOOLEAN",
    93: "TIMESTAMP",
    92: "TIME",
    91: "DATE",
    -4: "BYTEA",
    -3: "BYTEA",
    -2: "BYTEA",
    2004: "BYTEA"
}

MYSQL_TYPES = {
    12: "VARCHAR",
    1: "VARCHAR", 
    -1: "VARCHAR",
    -9: "VARCHAR",
    -15: "VARCHAR",
    -16: "VARCHAR",

    -5: "BIGINT",
    -6: "TINYINT",
    5: "SMALLINT",

    4: "INT",
    2: "DECIMAL",
    3: "DECIMAL",

    7: "FLOAT",
    8: "DOUBLE",
    6: "DOUBLE",

    -7: "BOOLEAN",
    16: "BOOLEAN",

    93: "DATETIME",
    92: "TIME",
    91: "DATE",

    -4: "BLOB",
    -3: "BLOB",
    -2: "BLOB",
    2004: "BLOB"
}

PYTHON_TYPES = {
    12: str,
    1: str,
    -1: str,
    -9: str,
    -15: str,
    -16: str,
    -5: int,
    -6: int,
    5: int,
    4: int,
    2: float,
    3: float,
    7: float,
    8: float,
    6: float,
    -7: bool,
    16: bool,
    93: datetime,
    92: time, 
    91: str, 
    -4: bytes,
    -3: bytes,
    -2: bytes,
    2004: bytes
}