import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


BASE_DIR = Path(__file__).resolve().parent.parent


class Config:
    APP_HOST = os.getenv("APP_HOST", "127.0.0.1")
    APP_PORT = int(os.getenv("APP_PORT", 5000))
    DEBUG = os.getenv("DEBUG", "True") == "True"
    SECRET_KEY = os.getenv("SECRET_KEY", "default").strip()
    LOGIN_PASSWORD = os.getenv("LOGIN_PASSWORD", "").strip()
    LOGIN_ENABLED = bool(LOGIN_PASSWORD)
    DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///data/app.db")
    UPLOAD_FOLDER = str(BASE_DIR / "data" / "uploads")
    MAX_CONTENT_LENGTH = int(os.getenv("MAX_CONTENT_LENGTH", 10 * 1024 * 1024))
    LOG_FILE_PATH = os.getenv("LOG_FILE_PATH", "logs/worker.log")
    PLAYWRIGHT_HEADLESS = os.getenv("PLAYWRIGHT_HEADLESS", "False").lower() == "true"
    PLAYWRIGHT_AUTH_FILE = os.getenv(
        "PLAYWRIGHT_AUTH_FILE",
        str(BASE_DIR / "playwright" / ".auth" / "reddit.json")
    )
    WORKER_POLL_SECONDS = int(os.getenv("WORKER_POLL_SECONDS", 30))
    DEBUG_ARTIFACTS_DIR = os.getenv("DEBUG_ARTIFACTS_DIR", "logs/debug")

    @classmethod
    def ensure_runtime_directories(cls) -> None:
        directories = [
            Path(cls.UPLOAD_FOLDER),
            Path(cls.LOG_FILE_PATH).expanduser().parent,
            Path(cls.DEBUG_ARTIFACTS_DIR).expanduser(),
            Path(cls.PLAYWRIGHT_AUTH_FILE).expanduser().parent,
        ]

        for directory in directories:
            if str(directory).strip():
                directory.mkdir(parents=True, exist_ok=True)

    if LOGIN_ENABLED and not SECRET_KEY:
        raise ValueError(
            "SECRET_KEY must be configured when LOGIN_PASSWORD is set."
        )
