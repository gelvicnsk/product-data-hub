"""Création de app.correction_request (demandes de correction du golden record)

Révision : 0001
Précédente :
Créée le : 2026-11-12
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "correction_request",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("product_id", sa.BigInteger(), nullable=False),
        sa.Column("field", sa.String(50), nullable=False),
        sa.Column("current_value", sa.Text()),
        sa.Column("proposed_value", sa.Text(), nullable=False),
        sa.Column("comment", sa.Text()),
        sa.Column("status", sa.String(20), nullable=False, server_default="open"),
        sa.Column("requested_by", sa.String(100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("reviewed_by", sa.String(100)),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("status IN ('open', 'accepted', 'rejected')", name="ck_correction_status"),
        sa.CheckConstraint(
            "field IN ('product_name', 'description', 'family', 'lifecycle_state', 'standard_price')",
            name="ck_correction_field",
        ),
        schema="app",
    )
    op.create_index("ix_correction_request_product_id", "correction_request", ["product_id"], schema="app")


def downgrade() -> None:
    op.drop_index("ix_correction_request_product_id", table_name="correction_request", schema="app")
    op.drop_table("correction_request", schema="app")
