import os
from uuid import uuid4

import pytest
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from alembic import command
from app import core
from app.api import app
from app.core import db


@pytest.fixture
def client(tmp_path, monkeypatch):
    url = (
        core.settings.database_url
        if os.getenv("TEST_POSTGRES") == "1"
        else f"sqlite:///{tmp_path / 'test.db'}"
    )
    admin = None
    schema = f"test_{uuid4().hex}"
    if os.getenv("TEST_POSTGRES") == "1":
        admin = core.make_engine(url)
        with admin.begin() as connection:
            connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            connection.execute(text(f"CREATE SCHEMA {schema}"))
        engine = core.make_engine(
            url, connect_args={"options": f"-csearch_path={schema},public"}
        )
    else:
        engine = core.make_engine(url)
    monkeypatch.setattr(core, "engine", engine)
    monkeypatch.setattr(core.settings, "approval_key", "test-reviewer")
    config = Config("alembic.ini")
    command.upgrade(config, "head")

    def override():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[db] = override
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()
        engine.dispose()
        if admin:
            with admin.begin() as connection:
                connection.execute(text(f"DROP SCHEMA {schema} CASCADE"))
            admin.dispose()
