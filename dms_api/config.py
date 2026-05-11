import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    mysql_host: str
    mysql_port: int
    mysql_database: str
    mysql_user: str
    mysql_password: str
    token_secret: str
    token_max_age_seconds: int

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            mysql_host=os.getenv("MYSQL_HOST", "127.0.0.1"),
            mysql_port=int(os.getenv("MYSQL_PORT", "3306")),
            mysql_database=os.getenv("MYSQL_DATABASE", "mes_production"),
            mysql_user=os.getenv("MYSQL_USER", ""),
            mysql_password=os.getenv("MYSQL_PASSWORD", ""),
            token_secret=os.getenv("DMS_TOKEN_SECRET", "dms-api-server"),
            token_max_age_seconds=int(os.getenv("DMS_TOKEN_MAX_AGE_SECONDS", "86400")),
        )
