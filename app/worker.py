import time
from datetime import datetime, timezone
from app.config import Config
from app.db import Base, init_db
import app.models
from app.repositories.scheduled_post_repository import ScheduledPostRepository
from app.services.reddit_playwright_publisher import RedditPlaywrightPublisher

POLL_SECONDS = 30

def run_once():
    repo = ScheduledPostRepository()
    now_utc = datetime.now(timezone.utc)

    due_posts = repo.get_due_pending_posts(now_utc)

    if not due_posts:
        print(f"[{now_utc.isoformat()}] No hay posts pendientes para publicar.")
        return

    publisher = RedditPlaywrightPublisher(
        auth_file="playwright/.auth/reddit.json"
    )

    for post in due_posts:
        print(f"[{now_utc.isoformat()}] Publicando post ID={post.id} en r/{post.subreddit} ...")

        try:
            final_url = publisher.publish(
                subreddit=post.subreddit,
                title=post.title,
                body=post.body,
                image_path=post.image_path,
            )
            repo.mark_posted(post.id, final_url)
            print(f"[{now_utc.isoformat()}] OK - Post ID={post.id} publicado: {final_url}")
        except Exception as ex:
            repo.mark_failed(post.id, str(ex))
            print(f"[{now_utc.isoformat()}] ERROR - Post ID={post.id}: {ex}")


def main():
    engine = init_db(Config.DATABASE_URL)
    Base.metadata.create_all(bind=engine)

    print("Worker iniciado. Esperando publicaciones programadas...")

    while True:
        try:
            run_once()
        except Exception as ex:
            print(f"[WORKER ERROR] {ex}")

        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()