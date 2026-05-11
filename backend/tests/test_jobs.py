from datetime import datetime

import pytest
import pytest_asyncio
from sqlalchemy import delete, select

from app.database.session import async_session_maker
from app.models.tables import Agent, Event, Finding, GraphSnapshot, Investigation, InvestigationJob, Source
from app.orchestration.jobs import InvestigationJobService


@pytest_asyncio.fixture(autouse=True)
async def clean_job_tables():
    async with async_session_maker() as db:
        for table in (Finding, Source, Agent, Event, GraphSnapshot, InvestigationJob, Investigation):
            await db.execute(delete(table))
        await db.commit()
    yield
    async with async_session_maker() as db:
        for table in (Finding, Source, Agent, Event, GraphSnapshot, InvestigationJob, Investigation):
            await db.execute(delete(table))
        await db.commit()


@pytest.mark.asyncio
async def test_enqueue_creates_single_job():
    investigation = Investigation(
        user_id="user-1",
        claim="A claim with enough length",
        selected_provider="openai",
        selected_model="gpt-4o",
    )
    async with async_session_maker() as db:
        db.add(investigation)
        await db.commit()
        await db.refresh(investigation)

    service = InvestigationJobService()
    first = await service.enqueue(investigation.id)
    second = await service.enqueue(investigation.id)

    assert first.id == second.id


@pytest.mark.asyncio
async def test_claim_next_job_marks_investigation_running():
    investigation = Investigation(
        user_id="user-2",
        claim="Another claim with enough length",
        selected_provider="openai",
        selected_model="gpt-4o",
    )
    async with async_session_maker() as db:
        db.add(investigation)
        await db.commit()
        await db.refresh(investigation)

    service = InvestigationJobService()
    await service.enqueue(investigation.id)
    job = await service._claim_next_job()

    assert job.status == "running"
    assert job.attempts == 1
    assert job.locked_at is not None
    async with async_session_maker() as db:
        row = await db.get(Investigation, investigation.id)
        assert row.status == "running"


@pytest.mark.asyncio
async def test_recover_interrupted_jobs_requeues_running_jobs():
    investigation = Investigation(
        user_id="user-3",
        claim="Recoverable claim with enough length",
        selected_provider="openai",
        selected_model="gpt-4o",
        status="running",
    )
    async with async_session_maker() as db:
        db.add(investigation)
        await db.commit()
        await db.refresh(investigation)
        db.add(
            InvestigationJob(
                investigation_id=investigation.id,
                status="running",
                attempts=1,
                locked_at=datetime.utcnow(),
            )
        )
        await db.commit()

    service = InvestigationJobService()
    await service.recover_interrupted_jobs()

    async with async_session_maker() as db:
        job = await db.scalar(select(InvestigationJob).where(InvestigationJob.investigation_id == investigation.id))
        row = await db.get(Investigation, investigation.id)
        assert job.status == "retrying"
        assert job.locked_at is None
        assert row.status == "queued"
