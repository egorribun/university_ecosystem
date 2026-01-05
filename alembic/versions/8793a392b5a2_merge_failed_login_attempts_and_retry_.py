from collections.abc import Sequence

revision: str = "8793a392b5a2"
down_revision: str | tuple[str, ...] | None = ("2025070100011", "202507100001")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
