"""
Centralized application configuration.

Why this pattern:
- Pydantic Settings gives us a single, *typed* source of truth for config,
  validated once at process start instead of `os.environ.get(...)` scattered
  across the codebase.
- `lru_cache` turns `get_settings()` into a singleton without global mutable
  state, and it's trivially overridable in tests via FastAPI's
  `app.dependency_overrides`.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        # Without this, fields declared with an env `alias` (e.g.
        # `alias="MAX_COMPETITORS"`) can *only* be set by that alias --
        # `Settings(max_competitors=2)` would be silently ignored and fall
        # back to the default. Tests (and any code) construct `Settings`
        # directly by field name, so both must work.
        populate_by_name=True,
    )

    # --- Anthropic / Claude -------------------------------------------------
    anthropic_api_key: str = Field(default="", alias="ANTHROPIC_API_KEY")
    # Only needed for identity-linked API keys (accounts with multiple
    # workspaces / SSO) -- a plain workspace-scoped key leaves this unset.
    anthropic_workspace_id: str | None = Field(default=None, alias="ANTHROPIC_WORKSPACE_ID")
    claude_model: str = Field(default="claude-sonnet-4-6", alias="CLAUDE_MODEL")
    claude_max_tokens: int = Field(default=2048, alias="CLAUDE_MAX_TOKENS")

    # --- App ------------------------------------------------------------
    app_env: Literal["development", "staging", "production"] = Field(
        default="development", alias="APP_ENV"
    )
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    allowed_origins: str = Field(default="http://localhost:5173", alias="ALLOWED_ORIGINS")

    # --- Rate limiting ----------------------------------------------------
    rate_limit_per_minute: int = Field(default=30, alias="RATE_LIMIT_PER_MINUTE")

    # --- Analysis graph tunables --------------------------------------------
    max_research_revisions: int = Field(default=2, alias="MAX_RESEARCH_REVISIONS")
    max_competitors: int = Field(default=4, alias="MAX_COMPETITORS")
    web_search_max_uses: int = Field(default=3, alias="WEB_SEARCH_MAX_USES")

    # --- LangSmith observability (optional) ---------------------------------
    # Off by default: `pydantic-settings` only populates *this* model, not
    # `os.environ`, so the app lifespan bridges these into the process
    # environment (see `main.py`) before the graph is built -- LangSmith's
    # tracer reads env vars directly, not anything we can pass it via API.
    langsmith_tracing: bool = Field(default=False, alias="LANGSMITH_TRACING")
    langsmith_api_key: str | None = Field(default=None, alias="LANGSMITH_API_KEY")
    langsmith_project: str = Field(
        default="fieldnote-competitive-intelligence", alias="LANGSMITH_PROJECT"
    )
    langsmith_endpoint: str | None = Field(default=None, alias="LANGSMITH_ENDPOINT")

    @field_validator("allowed_origins")
    @classmethod
    def _not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("ALLOWED_ORIGINS must not be empty")
        return v

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.allowed_origins.split(",") if origin.strip()]

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def langsmith_enabled(self) -> bool:
        return self.langsmith_tracing and bool(self.langsmith_api_key)


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide Settings singleton (cached after first call)."""
    return Settings()
