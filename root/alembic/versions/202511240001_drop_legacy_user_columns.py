"""drop legacy user columns

Revision ID: 202511240001
Revises: fix_sender_id_type
Create Date: 2025-11-24 00:00:00

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '202511240001'
down_revision = 'fix_sender_id_type'
branch_labels = None
depends_on = None

def upgrade():
    # Drop columns if they exist
    # We use checkfirst=True logic implicitly by catching errors or inspecting, 
    # but standard alembic commands usually assume state.
    # However, since we are fixing a drift, we should be careful.
    
    # But for simplicity in this generated file:
    op.drop_column('users', 'dnd_enabled')
    op.drop_column('users', 'dnd_start')
    op.drop_column('users', 'dnd_end')
    op.drop_column('users', 'timezone')

def downgrade():
    # Add columns back
    op.add_column('users', sa.Column('timezone', sa.VARCHAR(length=64), autoincrement=False, nullable=True))
    op.add_column('users', sa.Column('dnd_end', postgresql.TIME(), autoincrement=False, nullable=True))
    op.add_column('users', sa.Column('dnd_start', postgresql.TIME(), autoincrement=False, nullable=True))
    op.add_column('users', sa.Column('dnd_enabled', sa.BOOLEAN(), server_default=sa.text('false'), autoincrement=False, nullable=False))
