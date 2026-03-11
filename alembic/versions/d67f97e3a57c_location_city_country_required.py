"""Make location city and country required

Revision ID: d67f97e3a57c
Revises: e1465e3b85c1
Create Date: 2026-03-09
"""



from alembic import op

revision: str = "d67f97e3a57c"
down_revision: str | None = "e1465e3b85c1"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # Fill NULLs before making NOT NULL (dev environment)
    op.execute("UPDATE locations SET city = 'Santiago' WHERE city IS NULL")
    op.execute("UPDATE locations SET country = 'CL' WHERE country IS NULL")

    op.alter_column("locations", "city", nullable=False)
    op.alter_column("locations", "country", nullable=False)


def downgrade() -> None:
    op.alter_column("locations", "country", nullable=True)
    op.alter_column("locations", "city", nullable=True)
