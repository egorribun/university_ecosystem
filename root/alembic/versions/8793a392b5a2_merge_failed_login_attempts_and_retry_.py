from typing import Sequence, Union

revision: str = "8793a392b5a2"
down_revision: Union[str, tuple[str, ...], None] = ("202507010001", "202507100001")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
