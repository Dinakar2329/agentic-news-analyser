import pytest
from sqlalchemy import text

from app.database.session import async_session_maker


@pytest.mark.asyncio
async def test_runtime_unique_indexes_exist_for_concurrency_guards():
    async with async_session_maker() as db:
        result = await db.execute(text("PRAGMA index_list(api_keys)"))
        api_key_indexes = {row[1] for row in result.fetchall()}
        result = await db.execute(text("PRAGMA index_list(sources)"))
        source_indexes = {row[1] for row in result.fetchall()}

    assert "uq_api_keys_user_provider" in api_key_indexes
    assert "uq_sources_investigation_url" in source_indexes
