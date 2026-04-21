from datetime import datetime, timezone

import app.db as db
from app.models import ScheduledPost


class ScheduledPostRepository:
    def create(
        self,
        title: str,
        subreddit: str,
        scheduled_at_utc: datetime,
        body: str | None = None,
        image_path: str | None = None,
        timezone_name: str = "Europe/Madrid",
        nsfw: bool = False,
        spoiler: bool = False,
    ) -> ScheduledPost:
        now = datetime.now(timezone.utc)

        post = ScheduledPost(
            title=title,
            body=body,
            subreddit=subreddit,
            image_path=image_path,
            scheduled_at_utc=scheduled_at_utc,
            timezone=timezone_name,
            status="pending",
            attempts=0,
            max_attempts=3,
            error_message=None,
            reddit_post_id=None,
            reddit_post_url=None,
            nsfw=nsfw,
            spoiler=spoiler,
            created_at_utc=now,
            updated_at_utc=now,
            published_at_utc=None,
        )

        with db.SessionLocal() as session:
            session.add(post)
            session.commit()
            session.refresh(post)
            return post

    def get_all(self) -> list[ScheduledPost]:
        with db.SessionLocal() as session:
            posts = session.query(ScheduledPost).order_by(ScheduledPost.id.desc()).all()
            return posts