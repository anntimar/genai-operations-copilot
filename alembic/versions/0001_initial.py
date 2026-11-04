import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

from alembic import op

revision = "0001"
down_revision = None


def upgrade():
    if op.get_bind().dialect.name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "documents",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("category", sa.String(), nullable=False),
        sa.Column("effective_date", sa.Date(), nullable=False),
    )
    op.create_index("ix_documents_category", "documents", ["category"])
    op.create_index("ix_documents_effective_date", "documents", ["effective_date"])
    op.create_table(
        "chunks",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "document_id",
            sa.String(),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("page", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("embedding_profile", sa.String(), nullable=False),
        sa.Column("embedding", Vector(384), nullable=False),
    )
    op.create_index("ix_chunks_embedding_profile", "chunks", ["embedding_profile"])
    op.create_index("ix_chunks_document_id", "chunks", ["document_id"])
    op.create_table(
        "turns",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("timestamp", sa.Float(), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.Column("feedback", sa.Boolean()),
        sa.Column("approval", sa.String()),
    )
    op.create_index("ix_turns_session_id", "turns", ["session_id"])


def downgrade():
    for table in ("turns", "chunks", "documents"):
        op.drop_table(table)
