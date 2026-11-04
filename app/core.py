from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://copilot:copilot@localhost:5432/copilot"
    provider: str = "mock"
    model: str = ""
    api_key: str = ""
    model_url: str = ""
    embedding_url: str = ""
    embedding_model: str = ""
    embedding_api_key: str = ""
    timeout: float = 20
    input_usd_per_million: float = 0
    output_usd_per_million: float = 0
    approval_key: str = ""
    max_upload_bytes: int = 5 * 1024 * 1024


settings = Settings()


def make_engine(url: str, **kwargs):
    result = create_engine(url, pool_pre_ping=True, **kwargs)
    if result.dialect.name == "sqlite":

        @event.listens_for(result, "connect")
        def enable_foreign_keys(connection, _record):
            connection.execute("PRAGMA foreign_keys=ON")

    return result


engine = make_engine(settings.database_url)


def db():
    with Session(engine) as session:
        yield session
