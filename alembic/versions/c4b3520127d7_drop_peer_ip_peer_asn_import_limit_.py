"""Drop peer_ip, peer_asn, import_limit, export_limit from bgp_sessions

Revision ID: c4b3520127d7
Revises: 5be56e559ef7
Create Date: 2026-03-20 08:24:14.039068

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'c4b3520127d7'
down_revision: Union[str, None] = '5be56e559ef7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint('ck_bgp_sessions_peer_asn_positive', 'bgp_sessions', type_='check')
    op.drop_column('bgp_sessions', 'peer_ip')
    op.drop_column('bgp_sessions', 'peer_asn')
    op.drop_column('bgp_sessions', 'import_limit')
    op.drop_column('bgp_sessions', 'export_limit')


def downgrade() -> None:
    op.add_column('bgp_sessions', sa.Column('export_limit', sa.INTEGER(), autoincrement=False, nullable=True))
    op.add_column('bgp_sessions', sa.Column('import_limit', sa.INTEGER(), autoincrement=False, nullable=True))
    op.add_column('bgp_sessions', sa.Column('peer_asn', sa.INTEGER(), autoincrement=False, nullable=False))
    op.add_column('bgp_sessions', sa.Column('peer_ip', postgresql.INET(), autoincrement=False, nullable=False))
    op.create_check_constraint(
        'ck_bgp_sessions_peer_asn_positive', 'bgp_sessions', 'peer_asn > 0',
    )
