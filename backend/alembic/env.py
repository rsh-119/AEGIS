import asyncio
import sys
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# backend/ is the project root the app expects on sys.path (matches how
# `uvicorn app.main:app` and `python -m app.db.seed` are run) — alembic
# invokes this file directly, so it isn't on sys.path by default.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings  # noqa: E402
from app.core.database import Base  # noqa: E402
from app import models  # noqa: E402,F401  — registers all tables on Base.metadata

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
#
# disable_existing_loggers=False is REQUIRED here and is not a style choice.
# fileConfig() defaults to True, which sets .disabled = True on every logger
# that already exists at the moment it runs. This module is not only loaded by
# the `alembic` CLI — app/core/database.py::init_db() calls
# `command.upgrade(cfg, "head")` on every application startup, by which point
# all 26 `app.*` loggers have been created at import time.
#
# With the default, that call silently disabled the entire application's
# logging for the life of the process: no warnings, no errors, no structured
# JSON output, nothing. Measured after init_db() — 26/26 app loggers disabled,
# and app.main could no longer emit at ERROR.
#
# Several other controls quietly depended on that logging working, so the
# damage was wider than "logs are missing":
#   • /health/ready deliberately returns a GENERIC error and sends the real
#     driver exception to the logs — which went nowhere;
#   • the READONLY_MODE block warning, circuit-breaker trips, IndianAPI 429
#     backoff and AI provider failures were all invisible;
#   • Sentry's logging integration captures breadcrumbs from log records, so it
#     received none.
#
# It also made the test suite's log-hygiene assertions vacuous — caplog.records
# was always empty, so "assert password not in logs" compared against an empty
# string. See tests/test_log_capture.py.
#
# The `configure_logger` attribute lets the CALLER opt out entirely. That is
# what app/core/database.py::init_db() does, and it matters for a second reason
# beyond disabling loggers: fileConfig() also REPLACES the root handler with
# alembic.ini's, which silently swapped production's structured JSON formatter
# for the human-readable dev one for the rest of the process's life. Verified in
# the built container — the two log lines emitted before init_db() were JSON,
# and everything after it was not, so log ingestion would have received two
# parseable lines and then nothing but prose.
#
# The `alembic` CLI passes no attributes, so it keeps its own logging config.
if config.attributes.get("configure_logger", True) and config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

# Single source of truth for both the DB URL and the schema: the same
# Settings/Base the app itself uses (app/core/config.py, app/core/database.py)
# — no second hardcoded connection string to drift out of sync.
config.set_main_option("sqlalchemy.url", get_settings().database_url)
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """In this scenario we need to create an Engine
    and associate a connection with the context.

    """

    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""

    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
