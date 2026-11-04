from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str
    redis_url: str
    api_key: str
    secret_key: str
    dashboard_password: str
    port: int = 8000
    aruco_dict: str = "DICT_4X4_50"


@lru_cache
def get_settings() -> Settings:
    return Settings()
