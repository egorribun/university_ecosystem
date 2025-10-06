import os
import sys
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool
from sqlalchemy.engine import make_url
from alembic import context

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from app.models import models

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = models.Base.metadata

def get_url() -> str:
    url = config.get_main_option("sqlalchemy.url")
    if url:
        return url
    env_url = os.getenv("DATABASE_URL", "")
    if env_url:
        return env_url
    raise RuntimeError("Database URL is not configured for Alembic")

def run_migrations_offline() -> None:
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online() -> None:
    connectable = engine_from_config(
        {"sqlalchemy.url": get_url()},
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()