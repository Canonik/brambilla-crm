import os

os.environ.setdefault("DATABASE_URL", "postgresql://brambilla:brambilla@127.0.0.1:5433/brambilla")
os.environ.setdefault("CRM_TOKEN", "test-token")

import pytest
from fastapi.testclient import TestClient

from app import db
from app.main import app
from app.routers.admin import reset_database

H = {"Authorization": "Bearer test-token"}


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def api(client):
    reset_database()
    return client
