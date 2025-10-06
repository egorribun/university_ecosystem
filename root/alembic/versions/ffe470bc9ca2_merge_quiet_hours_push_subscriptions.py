from typing import Sequence, Union

revision: str = "ffe470bc9ca2"
down_revision: Union[str, tuple[str, ...], None] = ("23d991e593b5", "f9d2b1f5e2d0")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
