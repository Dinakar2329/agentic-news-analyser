"""Add uniqueness invariants for BYOK keys and sources.

Revision ID: 20260512_0002
Revises: 20260511_0001
Create Date: 2026-05-12
"""

from collections.abc import Sequence

from alembic import op


revision: str = "20260512_0002"
down_revision: str | None = "20260511_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        DELETE FROM api_keys
        WHERE id IN (
            SELECT id
            FROM (
                SELECT
                    id,
                    ROW_NUMBER() OVER (
                        PARTITION BY user_id, provider
                        ORDER BY COALESCE(last_validated_at, created_at) DESC, created_at DESC, id DESC
                    ) AS duplicate_rank
                FROM api_keys
            ) ranked
            WHERE duplicate_rank > 1
        )
        """
    )
    op.execute(
        """
        DELETE FROM findings
        WHERE source_id IN (
            SELECT id
            FROM (
                SELECT
                    id,
                    ROW_NUMBER() OVER (
                        PARTITION BY investigation_id, url
                        ORDER BY id ASC
                    ) AS duplicate_rank
                FROM sources
            ) ranked
            WHERE duplicate_rank > 1
        )
        """
    )
    op.execute(
        """
        DELETE FROM sources
        WHERE id IN (
            SELECT id
            FROM (
                SELECT
                    id,
                    ROW_NUMBER() OVER (
                        PARTITION BY investigation_id, url
                        ORDER BY id ASC
                    ) AS duplicate_rank
                FROM sources
            ) ranked
            WHERE duplicate_rank > 1
        )
        """
    )
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_api_keys_user_provider ON api_keys (user_id, provider)")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_sources_investigation_url ON sources (investigation_id, url)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_sources_investigation_url")
    op.execute("DROP INDEX IF EXISTS uq_api_keys_user_provider")
