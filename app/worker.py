import time
from datetime import datetime, timezone

from app.config import Config
from app.db import Base, init_db
import app.models
from app.repositories.scheduled_post_repository import ScheduledPostRepository
from app.services.logger_service import setup_logger
from app.services.reddit_playwright_publisher import RedditPlaywrightPublisher


POLL_SECONDS = Config.WORKER_POLL_SECONDS

logger = setup_logger(Config.LOG_FILE_PATH)


def log_info(message: str) -> None:
    logger.info(message)


def log_error(message: str) -> None:
    logger.error(message)


def run_once():
    repo = ScheduledPostRepository()

    # Fetch posts that are pending and scheduled for execution
    due_posts = repo.get_due_pending_posts(datetime.now(timezone.utc))

    if not due_posts:
        log_info("No pending posts to publish.")
        return

    publisher = RedditPlaywrightPublisher(
        auth_file=Config.PLAYWRIGHT_AUTH_FILE,
        headless=Config.PLAYWRIGHT_HEADLESS,
        debug_artifacts_dir=Config.DEBUG_ARTIFACTS_DIR,
    )

    for post in due_posts:
        # Try to lock the post for publishing
        locked = repo.mark_publishing(post.id)
        if not locked:
            log_info(f"Skipping post ID={post.id} because it is no longer pending.")
            continue

        log_info(
            f"Publishing post ID={post.id} "
            f"(subreddit={post.subreddit}, attempt={post.attempts + 1}/{post.max_attempts})"
        )

        try:
            # Execute publish
            final_url = publisher.publish(
                subreddit=post.subreddit,
                title=post.title,
                body=post.body,
                image_path=post.image_path,
            )

            # Mark as successfully published
            repo.mark_posted(post.id, final_url)
            log_info(f"SUCCESS - Post ID={post.id} published: {final_url}")

        except Exception as ex:
            # Mark failure and decide retry or final failure
            repo.mark_failed(post.id, str(ex))

            refreshed_post = repo.get_by_id(post.id)

            if refreshed_post and refreshed_post.status == "failed":
                log_error(f"FINAL ERROR - Post ID={post.id}: {ex}")
            else:
                log_error(f"RETRY ERROR - Post ID={post.id}: {ex}")


def main():
    # Initialize database
    engine = init_db(Config.DATABASE_URL)
    Base.metadata.create_all(bind=engine)

    log_info("Worker started. Waiting for scheduled posts...")

    while True:
        try:
            run_once()
        except Exception as ex:
            log_error(f"WORKER ERROR: {ex}")

        # Sleep between polling cycles
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()