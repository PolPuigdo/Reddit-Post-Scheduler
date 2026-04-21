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
        
    def get_by_id(self, post_id: int) -> ScheduledPost | None:
        with db.SessionLocal() as session:
            post = session.get(ScheduledPost, post_id)
            return post
        
    def cancel(self, post_id: int) -> bool:
        with db.SessionLocal() as session:
            post = session.get(ScheduledPost, post_id)

            if post is None:
                return False

            if post.status != "pending":
                return False

            post.status = "cancelled"
            post.updated_at_utc = datetime.now(timezone.utc)

            session.commit()
            return True
        
    def mark_posted(self, post_id: int, reddit_post_url: str) -> bool:
        with db.SessionLocal() as session:
            post = session.get(ScheduledPost, post_id)

            if post is None:
                return False

            post.status = "posted"
            post.reddit_post_url = reddit_post_url
            post.published_at_utc = datetime.now(timezone.utc)
            post.updated_at_utc = datetime.now(timezone.utc)
            post.error_message = None

            session.commit()
            return True

    def mark_failed(self, post_id: int, error_message: str) -> bool:
        with db.SessionLocal() as session:
            post = session.get(ScheduledPost, post_id)

            if post is None:
                return False

            post.status = "failed"
            post.error_message = error_message
            post.attempts += 1
            post.updated_at_utc = datetime.now(timezone.utc)

            session.commit()
            return True
        
    def get_due_pending_posts(self, now_utc: datetime) -> list[ScheduledPost]:
        with db.SessionLocal() as session:
            posts = (
                session.query(ScheduledPost)
                .filter(ScheduledPost.status == "pending")
                .filter(ScheduledPost.scheduled_at_utc <= now_utc)
                .order_by(ScheduledPost.scheduled_at_utc.asc())
                .all()
            )
            return posts