import os
from dataclasses import dataclass
from dotenv import load_dotenv
from farmSync.models import ServerDbConfig

load_dotenv()

@dataclass(frozen=True)
class Config:
    """
        Storage for env variables
    """
    baseUrl: str
    clientId: str
    clientSecret: str

def requireEnv(name: str) -> str:
    val = os.getenv(name)
    if not val:
        raise ValueError(f"Missing required env variable: {name}")
    return val


def loadConfig() -> Config:
    return Config(
    baseUrl = requireEnv("CF_BASE_URL"),
    clientId = requireEnv("CF_CLIENT_ID"),
    clientSecret = requireEnv("CF_CLIENT_SECRET")
    )

def loadDbConfig() -> ServerDbConfig:
    return ServerDbConfig(
        dbName = requireEnv("DB_NAME"),
        dbHost = requireEnv("DB_HOST"),
        dbPort = int(requireEnv("DB_PORT")),
        dbUser = requireEnv("DB_USER"),
        dbPassword = requireEnv("DB_PASSWORD")
    )
