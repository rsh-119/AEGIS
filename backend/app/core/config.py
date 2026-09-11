"""Application configuration loaded from environment / .env."""

from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # No hardcoded fallback on purpose (was previously a stale port-5433
    # default pointing at a since-decommissioned native Postgres install —
    # see MIGRATIONS.md) — DATABASE_URL must be set explicitly. Missing it
    # now fails loudly (pydantic-settings validation error) instead of
    # silently reconnecting to whatever used to be at the old default.
    database_url: str

    nvidia_api_key: str = ""
    nvidia_model: str = "deepseek-ai/deepseek-v4-flash"

    groq_api_key: str = ""
    groq_api_key_2: str = ""   # optional 2nd Groq key — doubles token budget
    groq_api_key_3: str = ""   # optional 3rd Groq key — triples token budget
    groq_model: str = "openai/gpt-oss-120b"

    @property
    def groq_keys(self) -> list[str]:
        """All configured Groq API keys, deduplicated."""
        keys = []
        for k in [self.groq_api_key, self.groq_api_key_2, self.groq_api_key_3]:
            if k and k not in keys:
                keys.append(k)
        return keys

    # ── Document analysis tiers (services/ai_service.py::analyze_document) ──
    # The frontend's concall/document UI offers three quality tiers and sends
    # legacy ids for them ("deepseek" = Deep Reasoning, "minimax" = Standard,
    # "groq" = Quick Read). Those ids are NOT model names and never were.
    #
    # They used to map to hardcoded Groq ids — qwen/qwen3-32b and
    # llama-3.1-8b-instant — both of which Groq has since dropped from its
    # catalog, so the "detailed" and "standard" tiers 404'd on every call and
    # fell through to the generic waterfall without anyone noticing. Model ids
    # belong in configuration for exactly that reason: a decommissioned model
    # should be a one-line env change, not a code change.
    #
    # Defaults are the two models verified live against Groq's /models catalog
    # and confirmed JSON-mode compliant (see ai_service.py's module docstring).
    # Set either to "" to disable that tier — it then falls through to the full
    # provider waterfall, which is the same behaviour as the tier failing.
    doc_model_detailed: str = "openai/gpt-oss-120b"
    doc_model_standard: str = "openai/gpt-oss-20b"

    openrouter_api_key: str = ""
    openrouter_model: str = "nvidia/nemotron-3-super-120b-a12b:free"

    # Free-tier key — used as a fast first attempt for the two interactive,
    # latency-sensitive AI paths only (portfolio review + portfolio ask), not
    # a general-purpose fallback. See ai_service.py's _call_gemini/prefer_gemini.
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.6-flash"

    redis_url: str = "redis://localhost:6379"
    indianapi_key: str = ""
    indianapi_enabled: bool = True   # set False when monthly quota is exhausted

    # Empty by default on purpose (no shared placeholder string) — main.py's
    # lifespan fails loudly at startup in production if this is still unset,
    # and generates a random per-process secret in development so local runs
    # keep working with zero config (tokens just won't survive a restart).
    jwt_secret_key: str = ""
    jwt_access_expire_minutes: int = 60          # 1 h access token
    jwt_refresh_expire_days: int = 30            # 30 d refresh token

    # Separate from jwt_secret_key on purpose — that secret signs every user's
    # session token, so reusing it as a bearer "admin key" means any leak of
    # this header (logs, a proxy, browser devtools) is equivalent to a full
    # auth bypass, not just an ops-panel leak. Empty by default: admin
    # endpoints fail closed in production until this is explicitly set.
    admin_api_key: str = ""

    app_env: str = "development"
    cors_origins: str = "http://localhost:3000"

    # Number of reverse proxies that append to X-Forwarded-For in front of
    # this app. Used to pick the client IP for rate limiting.
    #
    # uvicorn runs with --forwarded-allow-ips "*" (see backend/Dockerfile),
    # which makes it take the LEFTMOST X-Forwarded-For entry. That entry is
    # whatever the client sent, because each proxy *appends* the peer it saw
    # — so a client that supplies its own header controls request.client.host
    # and can reset every per-IP bucket at will. Counting from the right
    # instead lands on the value a trusted proxy actually wrote.
    #
    #   1 = one proxy (Render's edge / a k8s ingress) — the default, and the
    #       only value that is safe while the backend origin is reachable from
    #       the public internet.
    #   2 = browser -> Vercel edge -> Render, i.e. requests arriving through
    #       the Next.js /api/* rewrite.
    #
    # DECISION (2026-09-11): this stays at 1, and 2 is NOT recommended for the
    # current deployment. Raising it to 2 only pays off if EVERY request
    # reaches FastAPI through the Vercel rewrite. It does not: the Render
    # service URL is publicly resolvable, so an attacker can skip Vercel
    # entirely, connect to Render directly with `X-Forwarded-For: <anything>`,
    # and have Render's edge append their real peer — producing exactly two
    # entries, the leftmost of which is attacker-chosen. hops=2 would then read
    # that forged entry and the P1-1 bypass is back. See
    # tests/test_rate_limiting.py::test_two_hops_is_spoofable_from_a_direct_connection.
    #
    # The cost of staying at 1 is real and is a known limitation, not an
    # oversight: traffic arriving via the Vercel rewrite presents Vercel's
    # egress address, so those clients share one bucket instead of getting one
    # each. That is the safe direction to be wrong in (over-limiting, not
    # under-limiting), and per-account keying (user_or_ip_key) already covers
    # the expensive authenticated routes. Making hops=2 safe requires a
    # deployment change only the operator can make — putting the backend behind
    # the proxy so it has no public origin (Render private service, or an IP
    # allowlist) — at which point set this to 2 and re-run the rate-limit
    # suite.
    trusted_proxy_hops: int = 1

    # Which TCP peers are allowed to speak for someone else via
    # X-Forwarded-For, as a comma-separated list of IPs/CIDRs.
    #
    # trusted_proxy_hops alone is NOT sufficient, and believing otherwise was a
    # real gap: counting from the right only lands on a proxy-written entry if
    # a proxy actually appended one. Reach the app DIRECTLY — no proxy in the
    # path — and a single self-supplied `X-Forwarded-For: <anything>` is both
    # the first and the last entry, so hops=1 reads the attacker's value and
    # every per-IP limit is resettable again. Verified against the built
    # container: 40 logins with a rotating header produced zero 429s.
    #
    # That is not hypothetical. docker-compose.yml publishes the backend on
    # host port 8000 with nothing in front of it, and the README documents that
    # stack as a single-server deployment.
    #
    # So X-Forwarded-For is honoured only when the real socket peer is one of
    # these — the standard approach (nginx set_real_ip_from, Traefik
    # trustedIPs). The default covers loopback and the RFC1918 ranges a
    # reverse proxy, k8s ingress or Render's edge actually connects from; a
    # request arriving straight from the public internet has a public peer, so
    # its header is ignored and it is rate-limited on its true address.
    #
    # Getting this wrong in the strict direction is safe (clients behind the
    # proxy share one bucket); getting it wrong in the permissive direction is
    # not. Set to "*" only if the app is genuinely unreachable except through
    # a proxy — that turns the check off.
    #
    # NOTE: this requires uvicorn NOT to rewrite request.client.host, which is
    # why backend/Dockerfile no longer passes --forwarded-allow-ips "*".
    trusted_proxy_ips: str = "127.0.0.0/8,::1/128,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16,fc00::/7"

    @property
    def trusted_proxy_networks(self) -> list:
        import ipaddress
        nets = []
        for raw in self.trusted_proxy_ips.split(","):
            raw = raw.strip()
            if not raw:
                continue
            if raw == "*":
                return ["*"]
            try:
                nets.append(ipaddress.ip_network(raw, strict=False))
            except ValueError:
                continue      # a malformed entry must narrow trust, never widen it
        return nets

    # /metrics carries no secrets (asserted in tests/test_ops.py) but does
    # expose route inventory, traffic volume and latency distributions. In
    # production it is therefore behind the same X-Admin-Key as /health/status.
    # Set METRICS_PUBLIC=true only when the scrape path is network-isolated
    # (in-cluster Prometheus that cannot be reached from outside), which is the
    # case k8s/deployment.yaml's prometheus.io/scrape annotation describes.
    metrics_public: bool = False

    ai_timeout_seconds: int = 60
    news_api_key: str = ""

    # ── Operations & Reliability ──────────────────────────────────────────────
    readonly_mode: bool = False          # Firegun: blocks all write ops when True
    rate_limit_enabled: bool = True      # Toggle slowapi rate limiting
    log_level: str = "INFO"             # DEBUG | INFO | WARNING | ERROR

    # Empty by default: error tracking (Sentry) stays off until a real DSN is
    # set, same fail-closed-until-configured pattern as admin_api_key above.
    sentry_dsn: str = ""

    # ── Password reset (services/email_service.py) ──────────────────────────
    # Empty by default: forgot-password logs the reset link at INFO instead of
    # emailing it, same fail-closed-until-configured pattern as sentry_dsn.
    resend_api_key: str = ""
    email_from_address: str = "Aegis <noreply@yourdomain.com>"
    # Used to build the reset link (frontend_url + "/reset-password?token=...").
    frontend_url: str = "http://localhost:3000"

    # ── 2FA (core/totp.py) ───────────────────────────────────────────────────
    # Fernet key encrypting totp_secret at rest. Empty by default: /2fa/setup
    # 501s until this is set — a TOTP secret must be decryptable to generate
    # codes, so (unlike a password) it can't just be hashed, and shipping it
    # without an encryption key would mean storing it plaintext.
    totp_encryption_key: str = ""

    # ── Google Sign-In (core/oauth.py) ───────────────────────────────────────
    google_client_id: str = ""       # also exposed to the frontend as NEXT_PUBLIC_GOOGLE_CLIENT_ID
    google_client_secret: str = ""   # unused by the ID-token flow; reserved for a future auth-code flow

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
