import asyncio
import os
import tempfile
from pathlib import Path

_TEST_DB_FILE = Path(tempfile.gettempdir()) / "agentic_factcheck_pytest.db"
if _TEST_DB_FILE.exists():
    _TEST_DB_FILE.unlink()

os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_TEST_DB_FILE.as_posix()}"
os.environ.setdefault("ENVIRONMENT", "development")

import pytest

from app.database.session import engine
from app.models.tables import Base


@pytest.fixture(scope="session", autouse=True)
def _create_test_schema():
    async def _init():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(_init())
    yield
    if _TEST_DB_FILE.exists():
        try:
            _TEST_DB_FILE.unlink()
        except OSError:
            pass
