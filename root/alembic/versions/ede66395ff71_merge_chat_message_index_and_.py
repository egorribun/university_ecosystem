"""merge_chat_message_index_and_partitioning

Revision ID: ede66395ff71
Revises: 202512230001_chat_message_index, 6a898bba5589
Create Date: 2025-12-23 11:54:48.110013

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ede66395ff71'
down_revision: Union[str, None] = ('202512230001_chat_message_index', '6a898bba5589')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
