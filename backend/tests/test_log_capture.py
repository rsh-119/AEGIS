"""Canary: prove the test suite can actually see log output.

Every "no secret appears in the logs" assertion in this suite is of the form
`assert secret not in "\\n".join(r.getMessage() for r in caplog.records)`. If
`caplog.records` is empty, that string is empty and the assertion passes
whatever the application logs.

That is exactly what was happening: `configure_logging()` runs at `app.main`
import time and calls `root.handlers.clear()`, removing pytest's
LogCaptureHandler before any test ran. The log-hygiene tests were reported as
verified while inspecting nothing at all.

conftest's `_restore_caplog_handler` fixture puts the handler back. These tests
fail loudly if that ever stops working, rather than letting the hygiene tests
quietly go vacuous again.
"""

from __future__ import annotations

import logging

import pytest


def test_caplog_captures_application_loggers(caplog):
    with caplog.at_level(logging.DEBUG):
        logging.getLogger("app.main").warning("CANARY-app-main-%s", 1)
    msgs = [r.getMessage() for r in caplog.records]
    assert any("CANARY-app-main-1" in m for m in msgs), (
        "caplog captured nothing — every log-hygiene assertion in this suite "
        f"is now vacuous. Records: {msgs}"
    )


@pytest.mark.parametrize("level", [logging.DEBUG, logging.INFO, logging.WARNING])
def test_caplog_captures_at_every_level_the_hygiene_tests_use(level, caplog):
    """The hygiene tests use at_level(DEBUG); the suite's LOG_LEVEL is WARNING,
    so the root level must not drop those records before they are captured."""
    with caplog.at_level(logging.DEBUG):
        logging.getLogger("app.routers.auth").log(level, "CANARY-level-%s", level)
    msgs = [r.getMessage() for r in caplog.records]
    assert any(f"CANARY-level-{level}" in m for m in msgs), (
        f"records at level {logging.getLevelName(level)} were not captured: {msgs}"
    )


async def test_logs_emitted_from_inside_a_real_request_are_captured(client, caplog, monkeypatch):
    """End-to-end: a log line written by application code DURING a request must
    reach caplog. A canary on a bare logger would still pass if the app's own
    logging were disconnected from the root handler.

    ReadOnlyMiddleware is used because it logs unconditionally on a blocked
    write — unlike a successful request, which emits nothing in-process (there
    is no uvicorn access log behind ASGITransport). That absence is itself why
    the hygiene tests needed an explicit canary: "no records" and "no secret in
    the records" are indistinguishable otherwise.
    """
    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "readonly_mode", True)
    try:
        with caplog.at_level(logging.DEBUG):
            r = await client.post("/api/watchlist", json={"ticker": "TCS.NS"})
    finally:
        monkeypatch.setattr(settings, "readonly_mode", False)

    assert r.status_code == 503, "the request under test did not take the logging path"
    msgs = [rec.getMessage() for rec in caplog.records]
    assert any("READONLY MODE" in m for m in msgs), (
        "application code logged during a real request but nothing was "
        f"captured — the hygiene tests downstream are inspecting an empty "
        f"string. Records: {msgs}"
    )


def test_app_loggers_are_not_disabled_after_migrations_run(caplog):
    """Regression for the production defect this file exists because of.

    alembic/env.py calls fileConfig(), which defaults to
    disable_existing_loggers=True. init_db() runs it on EVERY application
    startup, after all `app.*` loggers already exist — so the default silenced
    the entire application's logging for the life of the process (26/26 loggers
    disabled, measured). alembic/env.py now passes
    disable_existing_loggers=False.

    The suite's own session fixture runs the same migration path, so by the
    time this executes the damage would already have been done.
    """
    disabled = [
        name for name in logging.root.manager.loggerDict
        if name.startswith("app.")
        and isinstance(logging.getLogger(name), logging.Logger)
        and logging.getLogger(name).disabled
    ]
    assert not disabled, (
        f"{len(disabled)} application loggers are disabled — the app is silent "
        f"in production and every log-based assertion here is vacuous: {disabled[:10]}"
    )


def test_alembic_env_does_not_disable_existing_loggers():
    """Pin the specific call, since the failure it causes is silent."""
    from pathlib import Path

    env_py = Path(__file__).resolve().parents[1] / "alembic" / "env.py"
    text = env_py.read_text()
    assert "disable_existing_loggers=False" in text, (
        "alembic/env.py calls fileConfig() without disable_existing_loggers=False. "
        "init_db() runs this at every startup and it will disable all app loggers."
    )


def test_migrations_do_not_replace_the_root_log_handler():
    """The second half of the same defect.

    fileConfig() does not only disable loggers — it also REPLACES the root
    handler with the one from alembic.ini. Since init_db() runs migrations on
    every startup, production's structured JSON formatter was swapped for the
    human-readable dev formatter for the rest of the process's life. Log
    ingestion would receive the two lines emitted before init_db() and then
    nothing parseable. Confirmed in the built container before the fix.
    """
    import logging
    from app.core.logging_config import _JsonFormatter, _PrettyFormatter

    root = logging.getLogger()
    assert root.handlers, "the root logger has no handlers at all"

    # Whichever formatter configure_logging() installed must still be one of
    # ours — not alembic.ini's generic logging.Formatter.
    formatters = [type(h.formatter) for h in root.handlers if h.formatter]
    assert any(f in (_JsonFormatter, _PrettyFormatter) for f in formatters), (
        f"the application's formatter was replaced during startup: {formatters}"
    )


def test_init_db_opts_out_of_alembic_logging_configuration():
    """Pin the mechanism, because both symptoms it prevents are silent."""
    import inspect
    from app.core import database

    src = inspect.getsource(database.init_db)
    assert 'cfg.attributes["configure_logger"] = False' in src, (
        "init_db() no longer opts out of Alembic's logging configuration — "
        "startup will disable every app logger and replace the root handler"
    )
