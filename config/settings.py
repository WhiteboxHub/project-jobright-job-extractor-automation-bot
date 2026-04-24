import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # Database
    DUCKDB_PATH: str = "data/job_engine.duckdb"
    
    # Browser
    CHROME_USER_DATA_DIR: str = "./chrome_profile"
    HEADLESS: bool = False

    # Proxy
    PROXY_URL: str | None = None

    # Safety
    MAX_APPLICATIONS_PER_RUN: int = 200
    SUBMISSION_COOLDOWN_SECONDS: int = 60
    DRY_RUN: bool = False
    KEEP_BROWSER_OPEN: bool = False
    SUBMIT_POST_CLICK_WAIT: int = 15

    # Authentication
    AUTH_URL: str | None = None
    AUTH_USERNAME: str | None = None
    AUTH_PASSWORD: str | None = None

    # Jobright scrape pacing
    JOBRIGHT_RANDOM_PAUSE_MIN_SEC: float = 3.0
    JOBRIGHT_RANDOM_PAUSE_MAX_SEC: float = 7.0
    JOBRIGHT_SCROLL_STEP_MIN_SEC: float = 1.5
    JOBRIGHT_SCROLL_STEP_MAX_SEC: float = 3.5
    JOBRIGHT_STEP2_PAUSE_MIN_SEC: float = 2.0
    JOBRIGHT_STEP2_PAUSE_MAX_SEC: float = 5.0
    JOBRIGHT_STEP2_PAGE_SETTLE_MIN_SEC: float = 2.0
    JOBRIGHT_STEP2_PAGE_SETTLE_MAX_SEC: float = 4.0
    JOBRIGHT_STEP2_SHUFFLE_PENDING: bool = False
    JOBRIGHT_STEP2_BREAK_EVERY_N: int = 20
    JOBRIGHT_STEP2_LONG_BREAK_MIN_SEC: float = 15.0
    JOBRIGHT_STEP2_LONG_BREAK_MAX_SEC: float = 30.0
    JOBRIGHT_STEP2_MOUSE_JITTER: bool = False
    JOBRIGHT_PIPELINE_START_JITTER_MAX_SEC: float = 0.0

    # Email Reporting Setup
    SMTP_SERVER: str | None = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USERNAME: str | None = None
    SMTP_PASSWORD: str | None = None
    REPORT_RECEIVER_EMAIL: str | None = None
    SENDER_EMAIL: str | None = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    @property
    def chrome_profile_path(self) -> str:
        return str(Path(self.CHROME_USER_DATA_DIR).resolve())

settings = Settings()
