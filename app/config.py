import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


BASE_DIR = Path(__file__).resolve().parent.parent


class Config:
    APP_HOST = os.getenv("APP_HOST", "127.0.0.1")
    APP_PORT = int(os.getenv("APP_PORT", 5000))
    DEBUG = os.getenv("DEBUG", "True") == "True"
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
    