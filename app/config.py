from pydantic import (
    AliasChoices,
    Field,
    computed_field,
    field_serializer,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_DATABASE_URL = (
    "postgresql+psycopg2://postgres:postgres@localhost:5432/followthru"
)
DEFAULT_OPENAI_COMPATIBLE_BASE_URL = "https://api.openai.com/v1"
DEFAULT_GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai"
DEFAULT_OPENAI_MODEL = "gpt-4o-mini"
DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"
DEFAULT_TRANSCRIPTION_MODEL = "large-v3"
AUTO_LLM_PROVIDER = "auto"
OPENAI_COMPATIBLE_PROVIDER = "openai-compatible"
GEMINI_PROVIDER = "gemini"
PLACEHOLDER_MARKERS = (
    "your-",
    "your_",
    "replace-",
    "replace_",
    "placeholder",
    "changeme",
)


def _normalize_optional_setting(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        return None

    lowered = normalized.lower()
    if any(marker in lowered for marker in PLACEHOLDER_MARKERS):
        return None
    return normalized


def _normalize_optional_value(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _normalize_provider_name(value: str | None) -> str | None:
    normalized = _normalize_optional_value(value)
    if normalized is None:
        return None

    lowered = normalized.lower()
    if lowered in {"openai", OPENAI_COMPATIBLE_PROVIDER}:
        return OPENAI_COMPATIBLE_PROVIDER
    if lowered == GEMINI_PROVIDER:
        return GEMINI_PROVIDER
    if lowered == AUTO_LLM_PROVIDER:
        return AUTO_LLM_PROVIDER
    return lowered


def _looks_like_gemini_base_url(value: str | None) -> bool:
    normalized = _normalize_optional_value(value)
    if normalized is None:
        return False
    return "generativelanguage.googleapis.com" in normalized.lower()


class Settings(BaseSettings):
    app_name: str = "FollowThru"
    app_version: str = "1.0.0"
    app_env: str = "development"
    log_level: str = "INFO"
    database_pool_size: int = 5
    database_max_overflow: int = 10
    database_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices("DATABASE_URL", "SUPABASE_DB_URL"),
    )
    slack_bot_token: str | None = Field(
        default=None,
        validation_alias=AliasChoices("SLACK_BOT_TOKEN", "SLACK_TOKEN"),
    )
    slack_signing_secret: str | None = None
    slack_app_token: str | None = None
    llm_provider: str = AUTO_LLM_PROVIDER
    llm_base_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices("LLM_BASE_URL"),
    )
    llm_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("LLM_API_KEY"),
    )
    llm_model: str | None = Field(
        default=None,
        validation_alias=AliasChoices("LLM_MODEL"),
    )
    llm_timeout_seconds: float = Field(
        default=30.0,
        validation_alias=AliasChoices("LLM_TIMEOUT_SECONDS", "OPENAI_TIMEOUT_SECONDS"),
    )
    openai_base_url_setting: str | None = Field(
        default=None,
        validation_alias=AliasChoices("OPENAI_BASE_URL"),
    )
    openai_api_key_setting: str | None = Field(
        default=None,
        validation_alias=AliasChoices("OPENAI_API_KEY"),
    )
    openai_model_setting: str | None = Field(
        default=None,
        validation_alias=AliasChoices("OPENAI_MODEL"),
    )
    gemini_base_url_setting: str | None = Field(
        default=None,
        validation_alias=AliasChoices("GEMINI_BASE_URL"),
    )
    gemini_api_key_setting: str | None = Field(
        default=None,
        validation_alias=AliasChoices("GEMINI_API_KEY"),
    )
    gemini_model_setting: str | None = Field(
        default=None,
        validation_alias=AliasChoices("GEMINI_MODEL"),
    )
    transcription_base_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices("TRANSCRIPTION_BASE_URL"),
    )
    transcription_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("TRANSCRIPTION_API_KEY"),
    )
    transcription_model: str | None = Field(
        default=None,
        validation_alias=AliasChoices("TRANSCRIPTION_MODEL"),
    )
    transcription_timeout_seconds: float | None = Field(
        default=None,
        validation_alias=AliasChoices("TRANSCRIPTION_TIMEOUT_SECONDS"),
    )
    slack_publish_drafts: bool = True
    primary_slack_command: str = "/followthru"
    legacy_slack_command: str = "/zmanage"
    followthru_chat_history_limit: int = 12
    followthru_job_execution_mode: str = Field(
        default="celery",
        validation_alias=AliasChoices("FOLLOWTHRU_JOB_EXECUTION_MODE"),
    )
    redis_url: str = Field(default="redis://localhost:6379/0")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @model_validator(mode="before")
    @classmethod
    def infer_llm_provider(cls, data):
        if not isinstance(data, dict):
            return data

        explicit_provider = _normalize_provider_name(
            data.get("LLM_PROVIDER") or data.get("llm_provider")
        )
        if explicit_provider and explicit_provider != AUTO_LLM_PROVIDER:
            data["llm_provider"] = explicit_provider
            return data

        generic_api_key = _normalize_optional_setting(
            data.get("LLM_API_KEY") or data.get("llm_api_key")
        )
        generic_base_url = _normalize_optional_value(
            data.get("LLM_BASE_URL") or data.get("llm_base_url")
        )
        openai_api_key = _normalize_optional_setting(
            data.get("OPENAI_API_KEY") or data.get("openai_api_key_setting")
        )
        gemini_api_key = _normalize_optional_setting(
            data.get("GEMINI_API_KEY") or data.get("gemini_api_key_setting")
        )

        if generic_api_key:
            data["llm_provider"] = (
                GEMINI_PROVIDER
                if _looks_like_gemini_base_url(generic_base_url)
                else OPENAI_COMPATIBLE_PROVIDER
            )
            return data

        if openai_api_key:
            data["llm_provider"] = OPENAI_COMPATIBLE_PROVIDER
            return data

        if gemini_api_key:
            data["llm_provider"] = GEMINI_PROVIDER
            return data

        if any(
            _normalize_optional_value(data.get(key))
            for key in ("OPENAI_MODEL", "OPENAI_BASE_URL")
        ):
            data["llm_provider"] = OPENAI_COMPATIBLE_PROVIDER
            return data

        if any(
            _normalize_optional_value(data.get(key))
            for key in ("GEMINI_MODEL", "GEMINI_BASE_URL")
        ):
            data["llm_provider"] = GEMINI_PROVIDER
            return data

        data["llm_provider"] = OPENAI_COMPATIBLE_PROVIDER
        return data

    @field_validator("llm_provider", mode="before")
    @classmethod
    def normalize_llm_provider(cls, value: str | None) -> str:
        return _normalize_provider_name(value) or AUTO_LLM_PROVIDER

    @field_validator("database_url", mode="before")
    @classmethod
    def normalize_database_url(cls, value: str | None) -> str | None:
        return _normalize_optional_value(value)

    @field_validator(
        "slack_bot_token",
        "slack_signing_secret",
        "slack_app_token",
        "llm_api_key",
        "openai_api_key_setting",
        "gemini_api_key_setting",
        "transcription_api_key",
        mode="before",
    )
    @classmethod
    def normalize_secret_settings(cls, value: str | None) -> str | None:
        return _normalize_optional_setting(value)

    @field_validator(
        "llm_base_url",
        "llm_model",
        "openai_base_url_setting",
        "openai_model_setting",
        "gemini_base_url_setting",
        "gemini_model_setting",
        "transcription_base_url",
        "transcription_model",
        mode="before",
    )
    @classmethod
    def normalize_optional_text_settings(cls, value: str | None) -> str | None:
        return _normalize_optional_value(value)

    @field_validator("followthru_job_execution_mode", mode="before")
    @classmethod
    def normalize_job_execution_mode(cls, value: str | None) -> str:
        normalized = (_normalize_optional_value(value) or "celery").lower()
        if normalized not in {"celery", "threaded"}:
            return "celery"
        return normalized

    @computed_field
    @property
    def resolved_database_url(self) -> str:
        return self.database_url or DEFAULT_DATABASE_URL

    @computed_field
    @property
    def is_sqlite(self) -> bool:
        return self.resolved_database_url.startswith("sqlite")

    @computed_field
    @property
    def is_postgresql(self) -> bool:
        return self.resolved_database_url.startswith("postgresql")

    @computed_field
    @property
    def slack_configured(self) -> bool:
        return bool(self.slack_bot_token and self.slack_signing_secret)

    @computed_field
    @property
    def llm_configured(self) -> bool:
        return bool(self.resolved_llm_api_key)

    @computed_field
    @property
    def resolved_llm_base_url(self) -> str:
        if self.llm_api_key and self.llm_base_url:
            return self.llm_base_url.rstrip("/")

        if self.llm_provider == GEMINI_PROVIDER:
            return (self.gemini_base_url_setting or DEFAULT_GEMINI_BASE_URL).rstrip("/")

        if self.openai_base_url_setting:
            return self.openai_base_url_setting.rstrip("/")

        return DEFAULT_OPENAI_COMPATIBLE_BASE_URL

    @computed_field
    @property
    def resolved_llm_model(self) -> str:
        if self.llm_api_key and self.llm_model:
            return self.llm_model

        if self.llm_provider == GEMINI_PROVIDER:
            return self.gemini_model_setting or DEFAULT_GEMINI_MODEL

        if self.openai_model_setting:
            return self.openai_model_setting

        return DEFAULT_OPENAI_MODEL

    @computed_field
    @property
    def resolved_llm_api_key(self) -> str | None:
        if self.llm_api_key:
            return self.llm_api_key

        if self.llm_provider == GEMINI_PROVIDER:
            return self.gemini_api_key_setting

        return self.openai_api_key_setting

    @computed_field
    @property
    def openai_configured(self) -> bool:
        return bool(self.openai_api_key_setting) or bool(
            self.llm_api_key and self.llm_provider == OPENAI_COMPATIBLE_PROVIDER
        )

    @computed_field
    @property
    def gemini_configured(self) -> bool:
        return bool(self.gemini_api_key_setting) or bool(
            self.llm_api_key and self.llm_provider == GEMINI_PROVIDER
        )

    @property
    def openai_api_key(self) -> str | None:
        return self.resolved_llm_api_key

    @property
    def openai_model(self) -> str:
        return self.resolved_llm_model

    @property
    def openai_timeout_seconds(self) -> float:
        return self.llm_timeout_seconds

    @computed_field
    @property
    def transcription_configured(self) -> bool:
        return bool(
            self.resolved_transcription_api_key and self.resolved_transcription_base_url
        )

    @property
    def resolved_transcription_api_key(self) -> str | None:
        if self.transcription_api_key:
            return self.transcription_api_key

        if self.llm_provider == OPENAI_COMPATIBLE_PROVIDER:
            return self.resolved_llm_api_key

        return self.openai_api_key_setting

    @property
    def resolved_transcription_base_url(self) -> str | None:
        if self.transcription_base_url:
            return self.transcription_base_url.rstrip("/")

        if (
            self.llm_provider == OPENAI_COMPATIBLE_PROVIDER
            and self.resolved_llm_api_key
        ):
            return self.resolved_llm_base_url

        if self.openai_api_key_setting:
            if self.openai_base_url_setting:
                return self.openai_base_url_setting.rstrip("/")
            return DEFAULT_OPENAI_COMPATIBLE_BASE_URL

        if self.transcription_api_key:
            if self.openai_base_url_setting:
                return self.openai_base_url_setting.rstrip("/")
            return DEFAULT_OPENAI_COMPATIBLE_BASE_URL

        return None

    @property
    def resolved_transcription_model(self) -> str:
        if self.transcription_model:
            return self.transcription_model

        if self.llm_provider == OPENAI_COMPATIBLE_PROVIDER and self.llm_api_key:
            if self.llm_model:
                return self.llm_model

        if self.openai_model_setting:
            return self.openai_model_setting

        return DEFAULT_TRANSCRIPTION_MODEL

    @property
    def resolved_transcription_timeout_seconds(self) -> float:
        if self.transcription_timeout_seconds is not None:
            return self.transcription_timeout_seconds
        return self.llm_timeout_seconds

    @field_serializer(
        "slack_bot_token",
        "slack_signing_secret",
        "slack_app_token",
    )
    def serialize_sensitive_values(self, value: str | None):
        return value


settings = Settings()
