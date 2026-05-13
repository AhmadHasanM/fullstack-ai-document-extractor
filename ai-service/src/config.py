import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BASE_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore"
    )

    # Database
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "postgresql://admin:admin123@localhost:5432/pdf_extractor"
    )

    # RabbitMQ
    RABBITMQ_URL: str = os.getenv(
        "RABBITMQ_URL",
        "amqp://guest:guest@localhost:5672/"
    )

    QUEUE_NAME: str = "pdf_processing_queue"

    # API Keys
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    DEEPSEK_API_KEY: str = os.getenv("DEEPSEK_API_KEY", "")

    # Detect running mode
    RUNNING_IN_DOCKER: bool = Path("/.dockerenv").exists()

    # Directories
    if Path("/.dockerenv").exists():
        UPLOADS_DIR: str = "/app/uploads"
        OUTPUTS_DIR: str = "/app/outputs"
    else:
        UPLOADS_DIR: str = str(PROJECT_ROOT / "uploads")
        OUTPUTS_DIR: str = str(PROJECT_ROOT / "outputs")

    MARKDOWN_DIR: str = os.path.join(OUTPUTS_DIR, "markdown")
    JSON_DIR: str = os.path.join(OUTPUTS_DIR, "json")
    IMAGES_DIR: str = os.path.join(OUTPUTS_DIR, "images")

    # Processing settings
    MAX_FILE_SIZE: int = 100 * 1024 * 1024
    CHUNK_SIZE: int = 1000
    CHUNK_OVERLAP: int = 200


settings = Settings()


def ensure_directories():
    directories = [
        settings.UPLOADS_DIR,
        settings.OUTPUTS_DIR,
        settings.MARKDOWN_DIR,
        settings.JSON_DIR,
        settings.IMAGES_DIR,
    ]

    for directory in directories:
        Path(directory).mkdir(parents=True, exist_ok=True)


ensure_directories()