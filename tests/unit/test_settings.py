from app.config import (
    DEFAULT_DATABASE_URL,
    DEFAULT_GEMINI_BASE_URL,
    DEFAULT_GEMINI_MODEL,
    Settings,
)


def _clear_llm_env(monkeypatch):
    for name in (
        "LLM_PROVIDER",
        "LLM_BASE_URL",
        "LLM_API_KEY",
        "LLM_MODEL",
        "LLM_TIMEOUT_SECONDS",
        "OPENAI_BASE_URL",
        "OPENAI_API_KEY",
        "OPENAI_MODEL",
        "OPENAI_TIMEOUT_SECONDS",
        "GEMINI_BASE_URL",
        "GEMINI_API_KEY",
        "GEMINI_MODEL",
        "TRANSCRIPTION_BASE_URL",
        "TRANSCRIPTION_API_KEY",
        "TRANSCRIPTION_MODEL",
        "TRANSCRIPTION_TIMEOUT_SECONDS",
        "FOLLOWTHRU_JOB_EXECUTION_MODE",
    ):
        monkeypatch.delenv(name, raising=False)


def test_settings_ignore_placeholder_credentials(monkeypatch):
    _clear_llm_env(monkeypatch)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-your-bot-token")
    monkeypatch.setenv("SLACK_SIGNING_SECRET", "your-signing-secret")
    monkeypatch.setenv("OPENAI_API_KEY", "your-openai-key")

    settings = Settings(_env_file=None)

    assert settings.resolved_database_url == DEFAULT_DATABASE_URL
    assert settings.is_postgresql
    assert not settings.slack_configured
    assert not settings.llm_configured
    assert not settings.openai_configured


def test_settings_support_openai_compatible_llm_aliases(monkeypatch):
    _clear_llm_env(monkeypatch)
    monkeypatch.setenv("LLM_BASE_URL", "https://api.groq.com/openai/v1")
    monkeypatch.setenv("LLM_API_KEY", "groq_live_key")
    monkeypatch.setenv("LLM_MODEL", "llama-3.1-8b-instant")
    monkeypatch.setenv("LLM_TIMEOUT_SECONDS", "12")

    settings = Settings(_env_file=None)

    assert settings.llm_configured
    assert settings.openai_configured
    assert settings.resolved_llm_base_url == "https://api.groq.com/openai/v1"
    assert settings.resolved_llm_api_key == "groq_live_key"
    assert settings.resolved_llm_model == "llama-3.1-8b-instant"
    assert settings.llm_timeout_seconds == 12
    assert settings.transcription_configured


def test_settings_infer_openai_compatible_provider_from_openai_aliases(monkeypatch):
    _clear_llm_env(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "openai_live_key")

    settings = Settings(_env_file=None)

    assert settings.llm_provider == "openai-compatible"
    assert settings.resolved_llm_api_key == "openai_live_key"


def test_settings_support_gemini_aliases_and_defaults(monkeypatch):
    _clear_llm_env(monkeypatch)
    monkeypatch.setenv("GEMINI_API_KEY", "gemini_live_key")

    settings = Settings(_env_file=None)

    assert settings.llm_configured
    assert settings.llm_provider == "gemini"
    assert settings.resolved_llm_api_key == "gemini_live_key"
    assert settings.resolved_llm_base_url == DEFAULT_GEMINI_BASE_URL
    assert settings.resolved_llm_model == DEFAULT_GEMINI_MODEL
    assert settings.gemini_configured
    assert not settings.openai_configured
    assert not settings.transcription_configured


def test_settings_prefer_openai_when_both_provider_keys_are_available(monkeypatch):
    _clear_llm_env(monkeypatch)
    monkeypatch.setenv("GEMINI_API_KEY", "gemini_live_key")
    monkeypatch.setenv("OPENAI_API_KEY", "openai_live_key")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-2.5-flash")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-4o-mini")

    settings = Settings(_env_file=None)

    assert settings.llm_provider == "openai-compatible"
    assert settings.resolved_llm_api_key == "openai_live_key"
    assert settings.resolved_llm_model == "gpt-4o-mini"
    assert settings.openai_configured
    assert settings.gemini_configured


def test_settings_respect_explicit_gemini_provider(monkeypatch):
    _clear_llm_env(monkeypatch)
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "gemini_live_key")
    monkeypatch.setenv("OPENAI_API_KEY", "openai_live_key")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-2.5-flash")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-4o-mini")

    settings = Settings(_env_file=None)

    assert settings.llm_provider == "gemini"
    assert settings.resolved_llm_api_key == "gemini_live_key"
    assert settings.resolved_llm_model == "gemini-2.5-flash"


def test_settings_support_threaded_job_execution_mode(monkeypatch):
    _clear_llm_env(monkeypatch)
    monkeypatch.setenv("FOLLOWTHRU_JOB_EXECUTION_MODE", "threaded")

    settings = Settings(_env_file=None)

    assert settings.followthru_job_execution_mode == "threaded"
