from sqlalchemy import create_engine, text
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


def run_schema_migrations() -> None:
    if engine is None:
        return

    if engine.dialect.name != "sqlite":
        return

    with engine.begin() as connection:
        table_exists = connection.execute(
            text(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='scheduled_posts'"
            )
        ).first()
        if table_exists is None:
            return

        columns = connection.execute(text("PRAGMA table_info('scheduled_posts')")).mappings().all()
        if not columns:
            return

        column_by_name = {row["name"]: row for row in columns}

        subreddit_info = column_by_name.get("subreddit")
        subreddit_not_null = subreddit_info is not None and int(subreddit_info["notnull"]) == 1

        has_target_type = "target_type" in column_by_name
        has_flair_id = "flair_id" in column_by_name
        has_flair_text = "flair_text" in column_by_name

        needs_rebuild = subreddit_not_null

        if needs_rebuild:
            connection.execute(text("PRAGMA foreign_keys=OFF"))
            connection.execute(
                text(
                    """
                    CREATE TABLE scheduled_posts__new (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        title VARCHAR(300) NOT NULL,
                        body TEXT,
                        subreddit VARCHAR(100),
                        target_type VARCHAR(20) NOT NULL DEFAULT 'subreddit',
                        flair_id VARCHAR(200),
                        flair_text VARCHAR(300),
                        image_path VARCHAR(500),
                        scheduled_at_utc DATETIME NOT NULL,
                        timezone VARCHAR(100) NOT NULL DEFAULT 'Europe/Madrid',
                        status VARCHAR(50) NOT NULL DEFAULT 'pending',
                        attempts INTEGER NOT NULL DEFAULT 0,
                        max_attempts INTEGER NOT NULL DEFAULT 3,
                        error_message TEXT,
                        reddit_post_id VARCHAR(100),
                        reddit_post_url VARCHAR(500),
                        nsfw BOOLEAN NOT NULL DEFAULT 0,
                        spoiler BOOLEAN NOT NULL DEFAULT 0,
                        created_at_utc DATETIME NOT NULL,
                        updated_at_utc DATETIME NOT NULL,
                        published_at_utc DATETIME
                    )
                    """
                )
            )
            connection.execute(
                text(
                    """
                    INSERT INTO scheduled_posts__new (
                        id,
                        title,
                        body,
                        subreddit,
                        target_type,
                        flair_id,
                        flair_text,
                        image_path,
                        scheduled_at_utc,
                        timezone,
                        status,
                        attempts,
                        max_attempts,
                        error_message,
                        reddit_post_id,
                        reddit_post_url,
                        nsfw,
                        spoiler,
                        created_at_utc,
                        updated_at_utc,
                        published_at_utc
                    )
                    SELECT
                        id,
                        title,
                        body,
                        subreddit,
                        CASE
                            WHEN subreddit IS NULL OR TRIM(subreddit) = '' THEN 'profile'
                            ELSE 'subreddit'
                        END AS target_type,
                        NULL AS flair_id,
                        NULL AS flair_text,
                        image_path,
                        scheduled_at_utc,
                        timezone,
                        status,
                        attempts,
                        max_attempts,
                        error_message,
                        reddit_post_id,
                        reddit_post_url,
                        nsfw,
                        spoiler,
                        created_at_utc,
                        updated_at_utc,
                        published_at_utc
                    FROM scheduled_posts
                    """
                )
            )
            connection.execute(text("DROP TABLE scheduled_posts"))
            connection.execute(text("ALTER TABLE scheduled_posts__new RENAME TO scheduled_posts"))
            connection.execute(text("PRAGMA foreign_keys=ON"))
            return

        if not has_target_type:
            connection.execute(
                text(
                    "ALTER TABLE scheduled_posts ADD COLUMN target_type VARCHAR(20) NOT NULL DEFAULT 'subreddit'"
                )
            )

        if not has_flair_id:
            connection.execute(
                text("ALTER TABLE scheduled_posts ADD COLUMN flair_id VARCHAR(200)")
            )

        if not has_flair_text:
            connection.execute(
                text("ALTER TABLE scheduled_posts ADD COLUMN flair_text VARCHAR(300)")
            )

        connection.execute(
            text(
                """
                UPDATE scheduled_posts
                SET target_type = CASE
                    WHEN subreddit IS NULL OR TRIM(subreddit) = '' THEN 'profile'
                    ELSE 'subreddit'
                END
                WHERE target_type IS NULL OR TRIM(target_type) = ''
                """
            )
        )


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
