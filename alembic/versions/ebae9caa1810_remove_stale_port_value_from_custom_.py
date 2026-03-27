"""Remove stale port value from custom_field_entity_type enum

Revision ID: ebae9caa1810
Revises: c4b3520127d7
Create Date: 2026-03-20 10:15:03.983087

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'ebae9caa1810'
down_revision: Union[str, None] = 'c4b3520127d7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Delete any custom field definitions that reference 'port' entity type
    op.execute("DELETE FROM custom_field_definitions WHERE entity_type = 'port'")

    # Rename old enum, create new one without 'port', migrate column, drop old
    op.execute("ALTER TYPE custom_field_entity_type RENAME TO custom_field_entity_type_old")
    op.execute("CREATE TYPE custom_field_entity_type AS ENUM ('member', 'connection', 'trunk', 'switch', 'vlan')")
    op.execute(
        "ALTER TABLE custom_field_definitions "
        "ALTER COLUMN entity_type TYPE custom_field_entity_type "
        "USING entity_type::text::custom_field_entity_type"
    )
    op.execute("DROP TYPE custom_field_entity_type_old")


def downgrade() -> None:
    op.execute("ALTER TYPE custom_field_entity_type RENAME TO custom_field_entity_type_old")
    op.execute("CREATE TYPE custom_field_entity_type AS ENUM ('member', 'connection', 'port', 'trunk', 'switch', 'vlan')")
    op.execute(
        "ALTER TABLE custom_field_definitions "
        "ALTER COLUMN entity_type TYPE custom_field_entity_type "
        "USING entity_type::text::custom_field_entity_type"
    )
    op.execute("DROP TYPE custom_field_entity_type_old")
