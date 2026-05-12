import os
from dataclasses import dataclass


def required_env(name: str) -> str:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        raise RuntimeError(
            f"Falta la variable {name}. Crea el archivo .env en la raiz de DMS_API_SERVER "
            "o define la variable de entorno antes de arrancar el servicio."
        )

    clean = value.strip()
    if clean in {"CAMBIAR_EN_SERVER", "change-me", "<password real>", "<cadena larga privada>"}:
        raise RuntimeError(
            f"La variable {name} todavia tiene un valor de ejemplo. Edita .env con el valor real."
        )
    return clean


def int_env(name: str, default: str) -> int:
    raw = os.getenv(name, default).strip()
    try:
        return int(raw)
    except ValueError as exc:
        raise RuntimeError(f"La variable {name} debe ser numerica. Valor actual: {raw}") from exc


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
            mysql_host=required_env("MYSQL_HOST"),
            mysql_port=int_env("MYSQL_PORT", "3306"),
            mysql_database=required_env("MYSQL_DATABASE"),
            mysql_user=required_env("MYSQL_USER"),
            mysql_password=required_env("MYSQL_PASSWORD"),
            token_secret=required_env("DMS_TOKEN_SECRET"),
            token_max_age_seconds=int_env("DMS_TOKEN_MAX_AGE_SECONDS", "86400"),
        )
