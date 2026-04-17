from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    anthropic_api_key: str = ""
    api_provider: str = "anthropic"
    model: str = "claude-sonnet-4-5-20250929"

    database_url: str = "postgresql+asyncpg://postgres:postgres@db:5432/computer_use"

    # Display numbers start at :10 so they don't clash with the host desktop (:0)
    display_start: int = 10
    vnc_base_port: int = 5910
    novnc_base_port: int = 6910
    novnc_web_path: str = "/opt/noVNC"

    # Sessions idle longer than this (minutes) are cleaned up by the GC task
    session_idle_timeout_minutes: int = 120

    max_tokens: int = 4096
    display_width: int = 1024
    display_height: int = 768


settings = Settings()
