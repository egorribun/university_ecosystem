"""remove author from news, add image_url

Revision ID: bd67902ca2cd
Revises: change_foreign_keys_ondelete
Create Date: 2025-06-14 06:36:56.799150

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'bd67902ca2cd'
down_revision: Union[str, None] = 'change_foreign_keys_ondelete'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    with op.batch_alter_table('news') as batch_op:
        batch_op.drop_constraint('news_author_id_fkey', type_='foreignkey')
        batch_op.drop_column('author_id')
        batch_op.add_column(sa.Column('image_url', sa.String(), nullable=True))

def downgrade() -> None:
    with op.batch_alter_table('news') as batch_op:
        batch_op.add_column(sa.Column('author_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('news_author_id_fkey', 'users', ['author_id'], ['id'])
        batch_op.drop_column('image_url')