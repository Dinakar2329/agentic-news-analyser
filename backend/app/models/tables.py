from datetime import datetime
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app.core.time import utcnow


def new_id() -> str:
    return str(uuid4())


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    api_keys: Mapped[list["ApiKey"]] = relationship(back_populates="user")


class ApiKey(Base):
    __tablename__ = "api_keys"
    __table_args__ = (Index("uq_api_keys_user_provider", "user_id", "provider", unique=True),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    provider: Mapped[str] = mapped_column(String(80), index=True)
    encrypted_key: Mapped[str] = mapped_column(Text)
    key_hint: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_validated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    user: Mapped[User] = relationship(back_populates="api_keys")


class Investigation(Base):
    __tablename__ = "investigations"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    claim: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(40), default="queued")
    selected_provider: Mapped[str] = mapped_column(String(80))
    selected_model: Mapped[str] = mapped_column(String(120))
    agent_count: Mapped[int] = mapped_column(Integer, default=3)
    search_depth: Mapped[int] = mapped_column(Integer, default=3)
    speed_accuracy: Mapped[int] = mapped_column(Integer, default=60)
    verdict: Mapped[str | None] = mapped_column(String(40), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class InvestigationJob(Base):
    __tablename__ = "investigation_jobs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    investigation_id: Mapped[str] = mapped_column(ForeignKey("investigations.id", ondelete="CASCADE"), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(40), default="queued", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    run_after: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class Event(Base):
    __tablename__ = "events"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    investigation_id: Mapped[str] = mapped_column(ForeignKey("investigations.id", ondelete="CASCADE"), index=True)
    type: Mapped[str] = mapped_column(String(80), index=True)
    payload_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Agent(Base):
    __tablename__ = "agents"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    investigation_id: Mapped[str] = mapped_column(ForeignKey("investigations.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(40), default="queued")
    task: Mapped[str] = mapped_column(Text)
    credibility_score: Mapped[float] = mapped_column(Float, default=0)
    progress: Mapped[float] = mapped_column(Float, default=0)


class Source(Base):
    __tablename__ = "sources"
    __table_args__ = (Index("uq_sources_investigation_url", "investigation_id", "url", unique=True),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    investigation_id: Mapped[str] = mapped_column(ForeignKey("investigations.id", ondelete="CASCADE"), index=True)
    agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id", ondelete="CASCADE"), index=True)
    url: Mapped[str] = mapped_column(Text)
    domain: Mapped[str] = mapped_column(String(255), index=True)
    title: Mapped[str] = mapped_column(Text)
    source_type: Mapped[str] = mapped_column(String(80))
    authenticity_score: Mapped[float] = mapped_column(Float)
    trust_score: Mapped[float] = mapped_column(Float)
    reliability_score: Mapped[float] = mapped_column(Float)
    bias_score: Mapped[float] = mapped_column(Float)
    official_badge: Mapped[bool] = mapped_column(Boolean, default=False)
    extracted_text: Mapped[str] = mapped_column(Text, default="")
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Finding(Base):
    __tablename__ = "findings"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    investigation_id: Mapped[str] = mapped_column(ForeignKey("investigations.id", ondelete="CASCADE"), index=True)
    agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id", ondelete="CASCADE"), index=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"), index=True)
    stance: Mapped[str] = mapped_column(String(40))
    summary: Mapped[str] = mapped_column(Text)
    evidence_json: Mapped[str] = mapped_column(Text)
    contradictions_json: Mapped[str] = mapped_column(Text)


class GraphSnapshot(Base):
    __tablename__ = "graph_snapshots"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    investigation_id: Mapped[str] = mapped_column(ForeignKey("investigations.id", ondelete="CASCADE"), index=True)
    nodes_json: Mapped[str] = mapped_column(Text)
    edges_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
