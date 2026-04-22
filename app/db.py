from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from pathlib import Path
from urllib.parse import unquote, urlparse

Base = declarative_base()

engine = None
SessionLocal = None


def init_db(database_url: str):
    global engine, SessionLocal

    _ensure_sqlite_parent_dir(database_url)

    engine = create_engine(
        database_url,
        echo=False,
        future=True
    )

    SessionLocal = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        future=True
    )

    return engine


def _ensure_sqlite_parent_dir(database_url: str) -> None:
    if not database_url.startswith("sqlite"):
        return

    parsed = urlparse(database_url)
    raw_path = unquote(parsed.path or "")

    if not raw_path or raw_path in {":memory:", "/:memory:"}:
        return

    candidate = raw_path

    # sqlite:///relative/path.db -> path comes as "/relative/path.db"
    if candidate.startswith("/") and not parsed.netloc:
        drive_letter_pattern = len(candidate) > 2 and candidate[1].isalpha() and candidate[2] == ":"
        if not drive_letter_pattern:
            candidate = candidate.lstrip("/")
        else:
            candidate = candidate[1:]

    db_file = Path(candidate)
    if not db_file.is_absolute():
        db_file = Path.cwd() / db_file

    db_file.parent.mkdir(parents=True, exist_ok=True)
