from datetime import datetime, timezone
from sqlalchemy import or_
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

    def get_all(
        self,
        q: str | None = None,
        status: str | None = None,
        scheduled_from_utc: datetime | None = None,
        scheduled_to_utc: datetime | None = None,
        sort_by: str = "id",
        sort_dir: str = "desc",
    ) -> list[ScheduledPost]:
        with db.SessionLocal() as session:
            query = session.query(ScheduledPost)

            if q:
                pattern = f"%{q}%"
                query = query.filter(
                    or_(
                        ScheduledPost.title.ilike(pattern),
                        ScheduledPost.subreddit.ilike(pattern),
                    )
                )

            if status:
                query = query.filter(ScheduledPost.status == status)

            if scheduled_from_utc is not None:
                query = query.filter(ScheduledPost.scheduled_at_utc >= scheduled_from_utc)

            if scheduled_to_utc is not None:
                query = query.filter(ScheduledPost.scheduled_at_utc <= scheduled_to_utc)

            sort_column = getattr(ScheduledPost, sort_by)
            order_clause = sort_column.asc() if sort_dir == "asc" else sort_column.desc()
            posts = query.order_by(order_clause).all()
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

    def delete_cancelled(self, post_id: int) -> bool:
        with db.SessionLocal() as session:
            post = session.get(ScheduledPost, post_id)

            if post is None:
                return False

            if post.status != "cancelled":
                return False

            session.delete(post)
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

            post.attempts += 1
            post.error_message = error_message
            post.updated_at_utc = datetime.now(timezone.utc)

            if post.attempts >= post.max_attempts:
                post.status = "failed"
            else:
                post.status = "pending"

            session.commit()
            return True
        
    def mark_publishing(self, post_id: int) -> bool:
        with db.SessionLocal() as session:
            post = session.get(ScheduledPost, post_id)

            if post is None:
                return False

            if post.status != "pending":
                return False

            post.status = "publishing"
            post.updated_at_utc = datetime.now(timezone.utc)

            session.commit()
            return True

    def update_pending(
        self,
        post_id: int,
        title: str,
        body: str | None,
        subreddit: str,
        scheduled_at_utc: datetime,
        image_path: str | None,
        reset_attempts: bool = True,
    ) -> bool:
        with db.SessionLocal() as session:
            post = session.get(ScheduledPost, post_id)

            if post is None:
                return False

            if post.status != "pending":
                return False

            post.title = title
            post.body = body
            post.subreddit = subreddit
            post.scheduled_at_utc = scheduled_at_utc
            post.image_path = image_path
            post.updated_at_utc = datetime.now(timezone.utc)

            if reset_attempts:
                post.attempts = 0
            post.error_message = None

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
