from sqlalchemy.engine import Connection


def ensure_database_invariants(connection: Connection) -> None:
    """Apply lightweight runtime invariants that create_all cannot add later."""
    _dedupe_existing_rows(connection)
    _create_unique_indexes(connection)


def _dedupe_existing_rows(connection: Connection) -> None:
    connection.exec_driver_sql(
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
    connection.exec_driver_sql(
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
    connection.exec_driver_sql(
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


def _create_unique_indexes(connection: Connection) -> None:
    connection.exec_driver_sql(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_api_keys_user_provider ON api_keys (user_id, provider)"
    )
    connection.exec_driver_sql(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_sources_investigation_url ON sources (investigation_id, url)"
    )
