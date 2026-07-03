"""Application configuration loaded from environment / .env."""

from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://aegis:aegis@127.0.0.1:5433/aegis"

    nvidia_api_key: str = ""
    nvidia_model: str = "deepseek-ai/deepseek-v4-flash"

    # MiniMax M2.7 — separate NVIDIA key, used as waterfall step between DeepSeek and OpenRouter
    nvidia_minimax_api_key: str = ""
    nvidia_minimax_model: str = "minimaxai/minimax-m2.7"

    groq_api_key: str = ""
    groq_api_key_2: str = ""   # optional 2nd Groq key — doubles token budget
    groq_api_key_3: str = ""   # optional 3rd Groq key — triples token budget
    groq_model: str = "llama-3.3-70b-versatile"

    @property
    def groq_keys(self) -> list[str]:
        """All configured Groq API keys, deduplicated."""
        keys = []
        for k in [self.groq_api_key, self.groq_api_key_2, self.groq_api_key_3]:
            if k and k not in keys:
                keys.append(k)
        return keys

    openrouter_api_key: str = ""
    openrouter_model: str = "openai/gpt-oss-120b:free"

    redis_url: str = "redis://localhost:6379"
    indianapi_key: str = ""
    indianapi_enabled: bool = True   # set False when monthly quota is exhausted

    jwt_secret_key: str = "change-me-in-production-use-openssl-rand-hex-32"
    jwt_access_expire_minutes: int = 60          # 1 h access token
    jwt_refresh_expire_days: int = 30            # 30 d refresh token

    app_env: str = "development"
    cors_origins: str = "http://localhost:3000"
    ai_timeout_seconds: int = 60
    news_api_key: str = ""

    # ── Operations & Reliability ──────────────────────────────────────────────
    readonly_mode: bool = False          # Firegun: blocks all write ops when True
    rate_limit_enabled: bool = True      # Toggle slowapi rate limiting
    log_level: str = "INFO"             # DEBUG | INFO | WARNING | ERROR

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
