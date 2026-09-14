from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Tafseer HAI API"
    gemini_api_key: str | None = None
    openrouter_api_key: str | None = None
    primary_model: str = "gemini-3.8-flash"
    openrouter_model: str = "openrouter/free"
    provider_mode: str = "free_first"
    knowledge_db_path: str = "knowledge/tafseer.db"
    max_questions: int = 3
    model_config = SettingsConfigDict(env_file=".env", env_prefix="TAFSEER_", extra="ignore")


settings = Settings()
