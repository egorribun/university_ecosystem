import typer

from app.cli import db, infra, migrate_passwords, tests

app = typer.Typer(
    help="University Ecosystem Unified CLI",
    add_completion=False,
    no_args_is_help=True,
)

# Add command groups
app.add_typer(db.app, name="db")
app.add_typer(infra.app, name="infra")
app.add_typer(tests.app, name="test")
app.add_typer(migrate_passwords.app, name="migrate-passwords")

if __name__ == "__main__":
    app()
