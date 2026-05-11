import asyncio
import logging
from datetime import datetime, timedelta

from sqlalchemy import select

from app.database.session import async_session_maker
from app.models.tables import Investigation, InvestigationJob
from app.orchestration.service import orchestrator


logger = logging.getLogger(__name__)


class InvestigationJobService:
    def __init__(self, poll_interval: float = 1.5):
        self.poll_interval = poll_interval
        self._stop_event = asyncio.Event()

    async def enqueue(self, investigation_id: str):
        async with async_session_maker() as db:
            existing = await db.scalar(
                select(InvestigationJob).where(InvestigationJob.investigation_id == investigation_id)
            )
            if existing:
                return existing
            job = InvestigationJob(investigation_id=investigation_id)
            db.add(job)
            await db.commit()
            await db.refresh(job)
            logger.info("investigation_job_enqueued id=%s investigation_id=%s", job.id, investigation_id)
            return job

    async def recover_interrupted_jobs(self):
        async with async_session_maker() as db:
            rows = await db.scalars(
                select(InvestigationJob).where(InvestigationJob.status == "running")
            )
            for job in rows:
                job.status = "retrying" if job.attempts < job.max_attempts else "failed"
                job.locked_at = None
                job.run_after = datetime.utcnow()
                investigation = await db.get(Investigation, job.investigation_id)
                if investigation and investigation.status == "running":
                    investigation.status = "queued" if job.status == "retrying" else "failed"
                logger.warning("investigation_job_recovered id=%s status=%s", job.id, job.status)
            await db.commit()

    async def run_forever(self):
        self._stop_event.clear()
        await self.recover_interrupted_jobs()
        while not self._stop_event.is_set():
            processed = await self.process_next()
            if not processed:
                try:
                    await asyncio.wait_for(self._stop_event.wait(), timeout=self.poll_interval)
                except TimeoutError:
                    pass

    def stop(self):
        self._stop_event.set()

    async def process_next(self) -> bool:
        job = await self._claim_next_job()
        if not job:
            return False
        try:
            await orchestrator.start(job.investigation_id)
        except Exception as exc:
            await self._mark_failed(job.id, exc)
        else:
            await self._mark_complete(job.id)
        return True

    async def _claim_next_job(self) -> InvestigationJob | None:
        async with async_session_maker() as db:
            now = datetime.utcnow()
            job = await db.scalar(
                select(InvestigationJob)
                .where(
                    InvestigationJob.status.in_(("queued", "retrying")),
                    InvestigationJob.run_after <= now,
                )
                .order_by(InvestigationJob.created_at.asc())
            )
            if not job:
                return None
            job.status = "running"
            job.locked_at = now
            job.attempts += 1
            investigation = await db.get(Investigation, job.investigation_id)
            if investigation:
                investigation.status = "running"
            await db.commit()
            await db.refresh(job)
            logger.info("investigation_job_claimed id=%s investigation_id=%s attempt=%s", job.id, job.investigation_id, job.attempts)
            return job

    async def _mark_complete(self, job_id: str):
        async with async_session_maker() as db:
            job = await db.get(InvestigationJob, job_id)
            if not job:
                return
            job.status = "complete"
            job.locked_at = None
            job.last_error = None
            await db.commit()
            logger.info("investigation_job_complete id=%s investigation_id=%s", job.id, job.investigation_id)

    async def _mark_failed(self, job_id: str, exc: Exception):
        async with async_session_maker() as db:
            job = await db.get(InvestigationJob, job_id)
            if not job:
                return
            job.locked_at = None
            job.last_error = str(exc)[:2000]
            investigation = await db.get(Investigation, job.investigation_id)
            if job.attempts >= job.max_attempts:
                job.status = "failed"
                if investigation:
                    investigation.status = "failed"
            else:
                job.status = "retrying"
                job.run_after = datetime.utcnow() + timedelta(seconds=min(60, 2**job.attempts * 5))
                if investigation:
                    investigation.status = "queued"
            await db.commit()
            logger.warning(
                "investigation_job_failed id=%s investigation_id=%s status=%s attempt=%s",
                job.id,
                job.investigation_id,
                job.status,
                job.attempts,
            )


job_service = InvestigationJobService()
