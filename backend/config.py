from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    secret_key: str
    site_admin_secret: str
    db_path: str = "data/gametime.db"
    base_url: str = "http://localhost:8000"
    event_expiry_days: int = 90
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "noreply@localhost"
    smtp_tls: bool = True


settings = Settings()
