"""Central application settings (Phase 1). Validates required env at import/lifespan."""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Any

from pydantic import AliasChoices, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _split_origins(value: str) -> list[str]:
    return [p.strip() for p in value.split(",") if p.strip()]


class Settings(BaseSettings):
    """App configuration. Secrets must never appear in logs or API responses (P1.4)."""

    model_config = SettingsConfigDict(
        env_file=(".env",),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = Field(validation_alias=AliasChoices("APP_ENV"))
    log_level: str = Field(default="info", validation_alias=AliasChoices("LOG_LEVEL"))

    api_base_url: str = Field(
        default="http://127.0.0.1:8000",
        validation_alias=AliasChoices("API_BASE_URL"),
    )
    frontend_base_url: str = Field(validation_alias=AliasChoices("FRONTEND_BASE_URL"))

    supabase_url: str = Field(validation_alias=AliasChoices("SUPABASE_URL"))
    supabase_service_role_key: str = Field(
        validation_alias=AliasChoices("SUPABASE_SERVICE_ROLE_KEY"),
    )
    supabase_anon_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("SUPABASE_ANON_KEY"),
    )

    # Declared for .env parity; not required for Phase 1 cold boot validation.
    gemini_api_key: str | None = Field(default=None, validation_alias=AliasChoices("GEMINI_API_KEY"))
    gemini_api_key_fallback: str | None = Field(
        default=None,
        validation_alias=AliasChoices("GEMINI_API_KEY_FALLBACK"),
    )
    gemini_model: str = Field(
        default="gemini-2.5-flash",
        validation_alias=AliasChoices("GEMINI_MODEL"),
    )
    groq_api_key: str | None = Field(default=None, validation_alias=AliasChoices("GROQ_API_KEY"))
    groq_api_key_fallback: str | None = Field(
        default=None,
        validation_alias=AliasChoices("GROQ_API_KEY_FALLBACK"),
    )

    default_timezone: str = Field(
        default="Asia/Kolkata",
        validation_alias=AliasChoices("DEFAULT_TIMEZONE"),
    )

    @field_validator("frontend_base_url", "supabase_url", "api_base_url")
    @classmethod
    def strip_urls(cls, v: str) -> str:
        return v.strip().rstrip("/")

    @model_validator(mode="after")
    def validate_phase1_required(self) -> Settings:
        missing: list[str] = []
        if not self.app_env:
            missing.append("APP_ENV")
        if not self.frontend_base_url:
            missing.append("FRONTEND_BASE_URL")
        if not self.supabase_url:
            missing.append("SUPABASE_URL")
        if not self.supabase_service_role_key:
            missing.append("SUPABASE_SERVICE_ROLE_KEY")
        if missing:
            raise ValueError(
                "Missing required environment variables for Phase 1: " + ", ".join(missing),
            )
        return self

    def cors_origins(self) -> list[str]:
        """Allow one or more frontend origins (comma-separated)."""
        return _split_origins(self.frontend_base_url)

    def safe_public_dict(self) -> dict[str, Any]:
        """Serializable snapshot for health/debug: no secrets (P1.4)."""
        return {
            "app_env": self.app_env,
            "log_level": self.log_level,
            "api_base_url": self.api_base_url,
            "frontend_base_url": self.frontend_base_url,
            "supabase_url": self.supabase_url,
            "supabase_configured": bool(self.supabase_url and self.supabase_service_role_key),
            "gemini_model": self.gemini_model,
            "default_timezone": self.default_timezone,
            "llm_keys_present": {
                "gemini_primary": bool(self.gemini_api_key),
                "gemini_fallback": bool(self.gemini_api_key_fallback),
                "groq_primary": bool(self.groq_api_key),
                "groq_fallback": bool(self.groq_api_key_fallback),
            },
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()


def clear_settings_cache() -> None:
    get_settings.cache_clear()


def load_settings_from_env(overrides: dict[str, str] | None = None) -> Settings:
    """Test helper: reload env-backed settings."""
    clear_settings_cache()
    if overrides:
        for k, v in overrides.items():
            os.environ[k] = v
    return get_settings()
