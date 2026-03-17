"""Rename member_type enum values to Spanish, add infraestructura_critica

Revision ID: a2c4e6f8b0d1
Revises: f7e8d9c0b1a2
Create Date: 2026-03-11
"""

from collections.abc import Sequence

from alembic import op

revision: str = "a2c4e6f8b0d1"
down_revision: str | None = "f7e8d9c0b1a2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Mapping: old English values -> new Spanish values
_RENAMES = [
    ("academic", "academico"),
    ("government", "gobierno"),
    ("corporate", "corporativo"),
    ("other", "otro"),
]


def upgrade() -> None:
    # Add new values first (PostgreSQL requires ADD VALUE outside transaction)
    op.execute("COMMIT")
    op.execute("ALTER TYPE member_type ADD VALUE IF NOT EXISTS 'academico'")
    op.execute("ALTER TYPE member_type ADD VALUE IF NOT EXISTS 'gobierno'")
    op.execute("ALTER TYPE member_type ADD VALUE IF NOT EXISTS 'corporativo'")
    op.execute("ALTER TYPE member_type ADD VALUE IF NOT EXISTS 'infraestructura_critica'")
    op.execute("ALTER TYPE member_type ADD VALUE IF NOT EXISTS 'otro'")
    op.execute("BEGIN")

    # Migrate existing rows from old values to new values
    for old, new in _RENAMES:
        op.execute(
            f"UPDATE members SET member_type = '{new}' "
            f"WHERE member_type = '{old}'"
        )

    # Recreate enum without old values:
    # 1. Change column to varchar
    op.execute(
        "ALTER TABLE members "
        "ALTER COLUMN member_type TYPE varchar(50) USING member_type::text"
    )
    # 2. Drop old enum
    op.execute("DROP TYPE member_type")
    # 3. Create new enum with only the correct values
    op.execute(
        "CREATE TYPE member_type AS ENUM "
        "('isp', 'cdn', 'ixp', 'academico', 'gobierno', "
        "'corporativo', 'infraestructura_critica', 'otro')"
    )
    # 4. Convert column back to enum
    op.execute(
        "ALTER TABLE members "
        "ALTER COLUMN member_type TYPE member_type USING member_type::member_type"
    )


def downgrade() -> None:
    # Reverse: rename Spanish values back to English, drop infraestructura_critica
    # Convert infraestructura_critica to other before removing
    op.execute(
        "UPDATE members SET member_type = 'otro' "
        "WHERE member_type = 'infraestructura_critica'"
    )

    # Change column to varchar
    op.execute(
        "ALTER TABLE members "
        "ALTER COLUMN member_type TYPE varchar(50) USING member_type::text"
    )
    # Rename back
    for old, new in _RENAMES:
        op.execute(
            f"UPDATE members SET member_type = '{old}' "
            f"WHERE member_type = '{new}'"
        )
    # Drop and recreate with old values
    op.execute("DROP TYPE member_type")
    op.execute(
        "CREATE TYPE member_type AS ENUM "
        "('isp', 'cdn', 'ixp', 'academic', 'government', 'corporate', 'other')"
    )
    op.execute(
        "ALTER TABLE members "
        "ALTER COLUMN member_type TYPE member_type USING member_type::member_type"
    )
