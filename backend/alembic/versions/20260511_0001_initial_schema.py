"""Initial Agentic FactCheck schema.

Revision ID: 20260511_0001
Revises:
Create Date: 2026-05-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260511_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "api_keys",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.String(length=80), nullable=False),
        sa.Column("encrypted_key", sa.Text(), nullable=False),
        sa.Column("key_hint", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("last_validated_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_api_keys_provider", "api_keys", ["provider"])
    op.create_index("ix_api_keys_user_id", "api_keys", ["user_id"])

    op.create_table(
        "investigations",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("claim", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("selected_provider", sa.String(length=80), nullable=False),
        sa.Column("selected_model", sa.String(length=120), nullable=False),
        sa.Column("agent_count", sa.Integer(), nullable=False),
        sa.Column("search_depth", sa.Integer(), nullable=False),
        sa.Column("speed_accuracy", sa.Integer(), nullable=False),
        sa.Column("verdict", sa.String(length=40), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_investigations_user_id", "investigations", ["user_id"])

    op.create_table(
        "investigation_jobs",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("investigation_id", sa.String(), sa.ForeignKey("investigations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("run_after", sa.DateTime(), nullable=False),
        sa.Column("locked_at", sa.DateTime(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_investigation_jobs_investigation_id", "investigation_jobs", ["investigation_id"], unique=True)
    op.create_index("ix_investigation_jobs_run_after", "investigation_jobs", ["run_after"])
    op.create_index("ix_investigation_jobs_status", "investigation_jobs", ["status"])

    op.create_table(
        "events",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("investigation_id", sa.String(), sa.ForeignKey("investigations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("type", sa.String(length=80), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_events_investigation_id", "events", ["investigation_id"])
    op.create_index("ix_events_type", "events", ["type"])

    op.create_table(
        "agents",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("investigation_id", sa.String(), sa.ForeignKey("investigations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("task", sa.Text(), nullable=False),
        sa.Column("credibility_score", sa.Float(), nullable=False),
        sa.Column("progress", sa.Float(), nullable=False),
    )
    op.create_index("ix_agents_investigation_id", "agents", ["investigation_id"])

    op.create_table(
        "sources",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("investigation_id", sa.String(), sa.ForeignKey("investigations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("agent_id", sa.String(), sa.ForeignKey("agents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("domain", sa.String(length=255), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("source_type", sa.String(length=80), nullable=False),
        sa.Column("authenticity_score", sa.Float(), nullable=False),
        sa.Column("trust_score", sa.Float(), nullable=False),
        sa.Column("reliability_score", sa.Float(), nullable=False),
        sa.Column("bias_score", sa.Float(), nullable=False),
        sa.Column("official_badge", sa.Boolean(), nullable=False),
        sa.Column("extracted_text", sa.Text(), nullable=False),
        sa.Column("published_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_sources_agent_id", "sources", ["agent_id"])
    op.create_index("ix_sources_domain", "sources", ["domain"])
    op.create_index("ix_sources_investigation_id", "sources", ["investigation_id"])

    op.create_table(
        "findings",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("investigation_id", sa.String(), sa.ForeignKey("investigations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("agent_id", sa.String(), sa.ForeignKey("agents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_id", sa.String(), sa.ForeignKey("sources.id", ondelete="CASCADE"), nullable=False),
        sa.Column("stance", sa.String(length=40), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("evidence_json", sa.Text(), nullable=False),
        sa.Column("contradictions_json", sa.Text(), nullable=False),
    )
    op.create_index("ix_findings_agent_id", "findings", ["agent_id"])
    op.create_index("ix_findings_investigation_id", "findings", ["investigation_id"])
    op.create_index("ix_findings_source_id", "findings", ["source_id"])

    op.create_table(
        "graph_snapshots",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("investigation_id", sa.String(), sa.ForeignKey("investigations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("nodes_json", sa.Text(), nullable=False),
        sa.Column("edges_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_graph_snapshots_investigation_id", "graph_snapshots", ["investigation_id"])


def downgrade() -> None:
    op.drop_index("ix_graph_snapshots_investigation_id", table_name="graph_snapshots")
    op.drop_table("graph_snapshots")
    op.drop_index("ix_findings_source_id", table_name="findings")
    op.drop_index("ix_findings_investigation_id", table_name="findings")
    op.drop_index("ix_findings_agent_id", table_name="findings")
    op.drop_table("findings")
    op.drop_index("ix_sources_investigation_id", table_name="sources")
    op.drop_index("ix_sources_domain", table_name="sources")
    op.drop_index("ix_sources_agent_id", table_name="sources")
    op.drop_table("sources")
    op.drop_index("ix_agents_investigation_id", table_name="agents")
    op.drop_table("agents")
    op.drop_index("ix_events_type", table_name="events")
    op.drop_index("ix_events_investigation_id", table_name="events")
    op.drop_table("events")
    op.drop_index("ix_investigation_jobs_status", table_name="investigation_jobs")
    op.drop_index("ix_investigation_jobs_run_after", table_name="investigation_jobs")
    op.drop_index("ix_investigation_jobs_investigation_id", table_name="investigation_jobs")
    op.drop_table("investigation_jobs")
    op.drop_index("ix_investigations_user_id", table_name="investigations")
    op.drop_table("investigations")
    op.drop_index("ix_api_keys_user_id", table_name="api_keys")
    op.drop_index("ix_api_keys_provider", table_name="api_keys")
    op.drop_table("api_keys")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
