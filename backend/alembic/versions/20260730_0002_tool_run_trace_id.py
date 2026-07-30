"""associate tool runs with agent response traces

Revision ID: 20260730_0002
Revises: 20260729_0001
Create Date: 2026-07-30
"""

import sqlalchemy as sa
from alembic import op


revision = "20260730_0002"
down_revision = "20260729_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tool_runs", sa.Column("trace_id", sa.Uuid(), nullable=True))
    op.create_index("ix_tool_runs_trace_id", "tool_runs", ["trace_id"])


def downgrade() -> None:
    op.drop_index("ix_tool_runs_trace_id", table_name="tool_runs")
    op.drop_column("tool_runs", "trace_id")
