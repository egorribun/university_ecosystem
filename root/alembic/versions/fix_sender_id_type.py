"""fix sender_id type

Revision ID: fix_sender_id_type
Revises: 96809b6dc35d
Create Date: 2025-11-23 02:17:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'fix_sender_id_type'
down_revision: Union[str, None] = '96809b6dc35d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Alter sender_id column type from VARCHAR to INTEGER
    op.execute('ALTER TABLE messages ALTER COLUMN sender_id TYPE INTEGER USING sender_id::INTEGER')
    
    # Also need to fix the chat_participants user_id if it's wrong
    op.execute('ALTER TABLE chat_participants ALTER COLUMN user_id TYPE INTEGER USING user_id::INTEGER')


def downgrade() -> None:
    """Downgrade schema."""
    op.execute('ALTER TABLE messages ALTER COLUMN sender_id TYPE VARCHAR')
    op.execute('ALTER TABLE chat_participants ALTER COLUMN user_id TYPE VARCHAR')
