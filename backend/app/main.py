from contextlib import asynccontextmanager
import asyncio

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.core.config import settings
from app.core.logging import configure_logging
from app.database.session import engine
from app.models.tables import Base
from app.orchestration.jobs import job_service


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.validate_production()
    configure_logging()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    job_worker = asyncio.create_task(job_service.run_forever())
    app.state.job_worker = job_worker
    yield
    job_service.stop()
    job_worker.cancel()
    try:
        await job_worker
    except asyncio.CancelledError:
        pass


app = FastAPI(
    title="Agentic FactCheck API",
    version="0.1.0",
    description="Real-time multi-agent news verification API.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "agentic-factcheck"}
