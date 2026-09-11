"""Shared test fixtures.

Environment is pinned BEFORE any `app.*` import, because config.get_settings()
is lru_cached and several modules bind `settings = get_settings()` at import
time. Everything external (IndianAPI, AI providers, Google, Resend) is either
disabled or given an obviously-fake key so an unmocked call fails loudly
instead of reaching a real service.

Backing stores are real, not fakes: Postgres `aegis_test` on the docker-compose
instance (port 5434) and Redis db 15 on the docker-compose instance (port 6380).

REQUIRES EXCLUSIVE ACCESS to that database and Redis db. `_clean_state`
TRUNCATEs every application table and FLUSHDBs Redis between tests, so two
suites running at once destroy each other's fixtures and produce a storm of
unrelated failures. Do not run this concurrently with another pytest process
or with pytest-xdist (`-n`) against the same DATABASE_URL/REDIS_URL. To
parallelise, give each worker its own database and Redis db via the
TEST_DATABASE_URL / TEST_REDIS_URL overrides below.
"""

from __future__ import annotations

import os

TEST_DB_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+asyncpg://aegis:aegis@localhost:5434/aegis_test"
)
TEST_REDIS_URL = os.environ.get("TEST_REDIS_URL", "redis://localhost:6380/15")

os.environ.update({
    "DATABASE_URL": TEST_DB_URL,
    "REDIS_URL": TEST_REDIS_URL,
    "APP_ENV": "development",
    "JWT_SECRET_KEY": "test-secret-key-that-is-at-least-32-chars-long",
    "ADMIN_API_KEY": "",
    "CORS_ORIGINS": "http://localhost:3000,https://aegis-rsh11.vercel.app",
    # External services — off or fake so nothing leaves the machine unmocked.
    "INDIANAPI_ENABLED": "false",
    "INDIANAPI_KEY": "fake-indianapi-key",
    "GROQ_API_KEY": "fake-groq-key",
    "GROQ_API_KEY_2": "",
    "GROQ_API_KEY_3": "",
    "OPENROUTER_API_KEY": "fake-openrouter-key",
    "NVIDIA_API_KEY": "fake-nvidia-key",
    "GEMINI_API_KEY": "",
    "RESEND_API_KEY": "",
    "SENTRY_DSN": "",
    "GOOGLE_CLIENT_ID": "test-client-id.apps.googleusercontent.com",
    # Fernet key for TOTP-at-rest tests (generated once, test-only).
    "TOTP_ENCRYPTION_KEY": "PqSVQwRuLNPl1hHLxT1MLyTHIrHoGl0h_4WQKvJyJqI=",
    "READONLY_MODE": "false",
    "RATE_LIMIT_ENABLED": "true",
    "LOG_LEVEL": "WARNING",
})

import asyncio  # noqa: E402
import uuid  # noqa: E402
from datetime import datetime, timedelta  # noqa: E402

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.core.auth import create_access_token, hash_password  # noqa: E402
from app.core.cache import cache  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.core.database import AsyncSessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Subscription, User  # noqa: E402

settings = get_settings()

_APP_TABLES = [
    "portfolio_reviews",
    "price_alerts",
    "watchlist",
    "holdings",
    "subscriptions",
    "ai_cache",
    "users",
]


# ── Session-wide setup ────────────────────────────────────────────────────────

@pytest.fixture(scope="session", autouse=True)
def _migrate_test_db():
    """Bring the dedicated test database to head via Alembic (never
    create_all) so the suite exercises the same schema production gets."""
    from alembic import command
    from alembic.config import Config
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    cfg = Config(str(root / "alembic.ini"))
    cfg.set_main_option("script_location", str(root / "alembic"))
    # Mirror init_db(): don't let Alembic reconfigure this process's logging.
    # Without it, fileConfig() strips pytest's capture handler and every
    # log-based assertion in the suite silently becomes vacuous.
    cfg.attributes["configure_logger"] = False
    cfg.set_main_option("sqlalchemy.url", TEST_DB_URL)
    command.upgrade(cfg, "head")
    yield


@pytest.fixture(autouse=True)
def _restore_caplog_handler(request):
    """Put pytest's log-capture handler back on the root logger.

    `app.core.logging_config.configure_logging()` runs at `app.main` import
    time and does `root.handlers.clear()` — correct for an application
    entrypoint (it stops duplicate handlers stacking up), but it also removes
    the LogCaptureHandler pytest installed, and `app.main` is imported by this
    very file before any test runs.

    The consequence was silent and serious: `caplog.records` was ALWAYS empty,
    so every log-hygiene assertion of the form "assert secret not in
    <joined log messages>" was comparing against an empty string and passing
    unconditionally. The suite reported that passwords, JWTs and reset tokens
    were verified absent from logs; nothing had actually been inspected.

    Re-attaching the handler per test makes those assertions real. There is a
    canary test (tests/test_log_capture.py) that fails if capture ever silently
    stops working again.
    """
    import logging

    plugin = request.config.pluginmanager.getplugin("logging-plugin")
    if plugin is None:                      # -p no:logging
        yield
        return

    root = logging.getLogger()
    added = []
    for handler in (plugin.caplog_handler, plugin.report_handler):
        if handler not in root.handlers:
            root.addHandler(handler)
            added.append(handler)
    # Records must be able to reach the handler at all: configure_logging sets
    # the root level from LOG_LEVEL (WARNING in this suite), which would drop
    # the DEBUG/INFO lines the hygiene tests need to inspect.
    previous_level = root.level
    root.setLevel(logging.DEBUG)
    try:
        yield
    finally:
        root.setLevel(previous_level)
        for handler in added:
            root.removeHandler(handler)


@pytest.fixture(scope="session", autouse=True)
def _connect_cache(_migrate_test_db):
    """Real Redis on db 15 — token_store, slowapi and cache.py all use it."""
    cache.connect(settings.redis_url)
    yield
    try:
        if cache._redis is not None:
            cache._redis.flushdb()
    except Exception:
        pass


@pytest_asyncio.fixture(autouse=True)
async def _clean_state(_connect_cache):
    """Truncate app tables and flush Redis db 15 between tests so no test can
    see another's rows, sessions or rate-limit buckets.

    The engine is disposed on teardown: `app.core.database.engine` is a
    module-level singleton whose pool would otherwise hold connections bound
    to a previous test's (now-closed) event loop.
    """
    async with engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {', '.join(_APP_TABLES)} RESTART IDENTITY CASCADE"))
    if cache._redis is not None:
        cache._redis.flushdb()
    cache._mem.flush()
    yield
    await engine.dispose()


@pytest_asyncio.fixture
async def db():
    async with AsyncSessionLocal() as session:
        yield session


# ── HTTP clients ──────────────────────────────────────────────────────────────

def _transport() -> ASGITransport:
    return ASGITransport(app=app, client=("203.0.113.10", 5555))


@pytest_asyncio.fixture
async def client():
    """Anonymous client. Each test gets a fresh cookie jar."""
    async with AsyncClient(transport=_transport(), base_url="http://testserver") as c:
        yield c


@pytest_asyncio.fixture
async def client_factory():
    """Build extra independent clients (separate cookie jars / source IPs)."""
    opened = []

    async def _make(ip: str = "203.0.113.10"):
        c = AsyncClient(
            transport=ASGITransport(app=app, client=(ip, 5555)),
            base_url="http://testserver",
        )
        opened.append(c)
        return c

    yield _make
    for c in opened:
        await c.aclose()


# ── User factories ────────────────────────────────────────────────────────────

VALID_PASSWORD = "CorrectHorse1!x"


async def _create_user(
    *,
    email: str | None = None,
    username: str | None = None,
    password: str | None = VALID_PASSWORD,
    is_admin: bool = False,
    pro: bool = False,
    is_active: bool = True,
    auth_provider: str = "local",
    google_id: str | None = None,
    pro_status: str = "active",
    pro_expires_at: datetime | None = None,
) -> User:
    suffix = uuid.uuid4().hex[:8]
    async with AsyncSessionLocal() as s:
        user = User(
            email=email or f"u{suffix}@example.com",
            username=username or f"user{suffix}",
            hashed_password=hash_password(password) if password else None,
            is_admin=is_admin,
            is_active=is_active,
            auth_provider=auth_provider,
            google_id=google_id,
        )
        s.add(user)
        await s.flush()
        if pro:
            s.add(Subscription(
                user_id=user.id, plan="pro", status=pro_status, expires_at=pro_expires_at,
            ))
        await s.commit()
        await s.refresh(user)
        return user


@pytest.fixture
def make_user():
    return _create_user


def auth_headers(user_id: int, session_id: str | None = None) -> dict[str, str]:
    """Bearer header for a user — the documented script/API client path."""
    return {"Authorization": f"Bearer {create_access_token(user_id, session_id or str(uuid.uuid4()))}"}


@pytest.fixture
def bearer():
    return auth_headers


@pytest_asyncio.fixture
async def user_a(make_user):
    return await make_user(email="a@example.com", username="usera")


@pytest_asyncio.fixture
async def user_b(make_user):
    return await make_user(email="b@example.com", username="userb")


@pytest_asyncio.fixture
async def pro_user(make_user):
    return await make_user(email="pro@example.com", username="prouser", pro=True)


@pytest_asyncio.fixture
async def admin_user(make_user):
    return await make_user(email="admin@example.com", username="adminuser", is_admin=True)


@pytest_asyncio.fixture
async def logged_in(client, user_a):
    """Cookie-authenticated client for user_a via the real /login endpoint."""
    r = await client.post("/api/auth/login", json={"email": user_a.email, "password": VALID_PASSWORD})
    assert r.status_code == 200, r.text
    return client, user_a


# ── Live server (real sockets — needed for SSE and perf) ──────────────────────

@pytest.fixture(scope="session")
def live_server(_migrate_test_db):
    """A real uvicorn process on a free port, started with the same proxy
    flags production uses. httpx's ASGITransport buffers whole responses, so
    open-ended streams and latency measurements need actual sockets."""
    import socket
    import subprocess
    import sys
    import time
    import urllib.error
    import urllib.request
    from pathlib import Path

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]

    env = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1])}
    # Flags mirror backend/Dockerfile's CMD so this reproduces production
    # rather than approximating it — asserted by
    # test_live_server.py::test_the_live_server_fixture_matches_the_dockerfile,
    # because this drifting is not hypothetical: the fixture kept
    # `--proxy-headers --forwarded-allow-ips "*"` after those flags were removed
    # from the Dockerfile, so the one suite that runs a REAL server was
    # exercising a configuration that no longer ships — and those are precisely
    # the flags whose removal closed the X-Forwarded-For bypass.
    #
    # --workers is left at 1 here, matching the Dockerfile, and the fixture's
    # purpose is real sockets and a real transport rather than multi-process
    # behaviour.
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app",
         "--host", "127.0.0.1", "--port", str(port),
         "--workers", "1",
         "--timeout-keep-alive", "10",
         "--no-server-header",
         "--log-level", "warning"],
        cwd=str(Path(__file__).resolve().parents[1]),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )

    base = f"http://127.0.0.1:{port}"
    deadline = time.time() + 45
    while time.time() < deadline:
        if proc.poll() is not None:
            out = proc.stdout.read().decode(errors="replace") if proc.stdout else ""
            raise RuntimeError(f"server died on startup:\n{out[-3000:]}")
        try:
            with urllib.request.urlopen(f"{base}/health/live", timeout=1):
                break
        except (urllib.error.URLError, OSError):
            time.sleep(0.25)
    else:
        proc.kill()
        raise RuntimeError("server did not become ready within 45s")

    yield base

    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()


# ── Misc helpers ──────────────────────────────────────────────────────────────

@pytest.fixture
def utcnow():
    return datetime.utcnow


def expired_token(user_id: int, token_type: str = "access") -> str:
    """Mint an already-expired token of the given type."""
    from jose import jwt
    from app.core.auth import ALGORITHM
    payload = {
        "sub": str(user_id),
        "type": token_type,
        "jti": str(uuid.uuid4()),
        "sid": str(uuid.uuid4()),
        "exp": datetime.utcnow() - timedelta(minutes=5),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=ALGORITHM)


@pytest.fixture
def event_loop_policy():
    return asyncio.get_event_loop_policy()
