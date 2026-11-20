"""WDH-070 source connectors and WDH-052 approved Odoo outbox."""

import sqlalchemy as sa
from alembic import op

revision = "0005_connectors"
down_revision = "0004_processing"
branch_labels = None
depends_on = None


def owned() -> list[sa.Column]:  # type: ignore[type-arg]
    return [
        sa.Column("id", sa.Uuid(as_uuid=False), primary_key=True),
        sa.Column("workspace_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "data_sources",
        *owned(),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("owner_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("token_hash", sa.String(64)),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("source_metadata", sa.JSON(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True)),
        sa.Column("last_cursor", sa.String(200)),
        sa.Column("failure_code", sa.String(80)),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"]),
        sa.UniqueConstraint("workspace_id", "id"),
        sa.UniqueConstraint("token_hash"),
        sa.CheckConstraint("kind IN ('personal_files','wecom_archive')"),
    )
    op.create_table(
        "source_receipts",
        *owned(),
        sa.Column("source_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("batch_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("cursor", sa.String(200), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.ForeignKeyConstraint(
            ["workspace_id", "source_id"], ["data_sources.workspace_id", "data_sources.id"]
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "batch_id"], ["ingest_batches.workspace_id", "ingest_batches.id"]
        ),
        sa.UniqueConstraint("workspace_id", "id"),
        sa.UniqueConstraint("source_id", "cursor"),
    )
    op.create_table(
        "odoo_deliveries",
        *owned(),
        sa.Column("entity_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("job_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("idempotency_key", sa.String(64), nullable=False),
        sa.Column("instance_hash", sa.String(64), nullable=False),
        sa.Column("target_model", sa.String(100), nullable=False),
        sa.Column("values", sa.JSON(), nullable=False),
        sa.Column("evidence_hash", sa.String(64), nullable=False),
        sa.Column("remote_id", sa.Integer()),
        sa.Column("read_back", sa.JSON()),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.ForeignKeyConstraint(
            ["workspace_id", "entity_id"],
            ["entity_assertions.workspace_id", "entity_assertions.id"],
        ),
        sa.ForeignKeyConstraint(["workspace_id", "job_id"], ["jobs.workspace_id", "jobs.id"]),
        sa.UniqueConstraint("workspace_id", "id"),
        sa.UniqueConstraint("workspace_id", "idempotency_key"),
        sa.UniqueConstraint("job_id"),
    )
    for table in ("data_sources", "source_receipts", "odoo_deliveries"):
        op.create_index(f"ix_{table}_workspace_id", table, ["workspace_id"])
    op.create_index("ix_source_receipts_source_id", "source_receipts", ["source_id"])


def downgrade() -> None:
    raise RuntimeError("Restore a verified backup with the matching application version")
