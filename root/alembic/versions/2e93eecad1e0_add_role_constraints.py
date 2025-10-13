"""add role constraints

Revision ID: 2e93eecad1e0
Revises: ffe470bc9ca2
Create Date: 2025-10-13 16:25:34.507376

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "2e93eecad1e0"
down_revision: Union[str, None] = "ffe470bc9ca2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


ROLE_VALUES = ("student", "teacher", "admin")


def upgrade() -> None:
    """Upgrade schema."""
    if op.get_context().dialect.name == "sqlite":
        return
    values_sql = ", ".join(f"'{value}'" for value in ROLE_VALUES)
    with op.batch_alter_table("users") as batch_op:
        batch_op.create_check_constraint(
            "ck_users_role_valid",
            f"role IN ({values_sql})",
        )
    with op.batch_alter_table("invite_codes") as batch_op:
        batch_op.create_check_constraint(
            "ck_invite_codes_role_valid",
            f"role IN ({values_sql})",
        )


def downgrade() -> None:
    """Downgrade schema."""
    if op.get_context().dialect.name == "sqlite":
        return
    with op.batch_alter_table("invite_codes") as batch_op:
        batch_op.drop_constraint("ck_invite_codes_role_valid", type_="check")
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_constraint("ck_users_role_valid", type_="check")
