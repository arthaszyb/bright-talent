import shutil
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
CONSOLE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CONSOLE_ROOT))

from console.api import build_app  # noqa: E402
from console.config import Config  # noqa: E402
from console.db import Database  # noqa: E402


@pytest.fixture()
def config(tmp_path):
    db_path = tmp_path / "console-test.db"
    return Config.from_args(repo=str(REPO_ROOT), port=0, db_path=str(db_path))


@pytest.fixture()
def db(config):
    database = Database(config.resolved_db_path)
    yield database
    database.close()


@pytest.fixture()
def app_client(config):
    from fastapi.testclient import TestClient

    app = build_app(config)
    with TestClient(app) as client:
        yield client
    # Clean up any workspaces this test run created.
    if config.workspaces_dir.exists():
        shutil.rmtree(config.workspaces_dir, ignore_errors=True)
