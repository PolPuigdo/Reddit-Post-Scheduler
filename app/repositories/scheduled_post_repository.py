from datetime import datetime, timezone
from sqlalchemy import or_
import app.db as db
from app.models import ScheduledPost, ScheduledPostImage


class ScheduledPostRepository:
    @staticmethod
    def _normalize_image_paths(
        image_paths: list[str] | None = None,
        image_path: str | None = None,
    ) -> list[str]:
        if image_paths is not None:
            return [path for path in image_paths if path]

        if image_path:
            return [image_path]

        return []

    def _ensure_legacy_image_attachment(self, session, post: ScheduledPost | None) -> bool:
        if post is None or not post.image_path:
            return False

        existing = (
            session.query(ScheduledPostImage.id)
            .filter(ScheduledPostImage.scheduled_post_id == post.id)
            .first()
        )
        if existing is not None:
            return False

        session.add(
            ScheduledPostImage(
                scheduled_post_id=post.id,
                image_path=post.image_path,
                position=1,
                created_at_utc=datetime.now(timezone.utc),
            )
        )
        return True

    def _replace_post_images(
        self,
        session,
        post: ScheduledPost,
        image_paths: list[str],
    ) -> None:
        (
            session.query(ScheduledPostImage)
            .filter(ScheduledPostImage.scheduled_post_id == post.id)
            .delete(synchronize_session=False)
        )

        now = datetime.now(timezone.utc)
        for index, path in enumerate(image_paths, start=1):
            session.add(
                ScheduledPostImage(
                    scheduled_post_id=post.id,
                    image_path=path,
                    position=index,
                    created_at_utc=now,
                )
            )

        post.image_path = image_paths[0] if image_paths else None

    def create(
        self,
        title: str,
        subreddit: str | None,
        target_type: str,
        scheduled_at_utc: datetime,
        body: str | None = None,
        image_paths: list[str] | None = None,
        image_path: str | None = None,
        timezone_name: str = "Europe/Madrid",
        nsfw: bool = False,
        spoiler: bool = False,
        flair_id: str | None = None,
        flair_text: str | None = None,
    ) -> ScheduledPost:
        now = datetime.now(timezone.utc)
        normalized_image_paths = self._normalize_image_paths(
            image_paths=image_paths,
            image_path=image_path,
        )

        post = ScheduledPost(
            title=title,
            body=body,
            subreddit=subreddit,
            target_type=target_type,
            flair_id=flair_id,
            flair_text=flair_text,
            image_path=normalized_image_paths[0] if normalized_image_paths else None,
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
            session.flush()

            self._replace_post_images(
                session=session,
                post=post,
                image_paths=normalized_image_paths,
            )

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
                        ScheduledPost.target_type.ilike(pattern),
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
            if post is None:
                return None

            changed = self._ensure_legacy_image_attachment(session, post)
            if changed:
                session.commit()
                post = session.get(ScheduledPost, post_id)

            return post

    def get_images(self, post_id: int) -> list[ScheduledPostImage]:
        with db.SessionLocal() as session:
            post = session.get(ScheduledPost, post_id)
            if post is None:
                return []

            changed = self._ensure_legacy_image_attachment(session, post)
            if changed:
                session.commit()

            images = (
                session.query(ScheduledPostImage)
                .filter(ScheduledPostImage.scheduled_post_id == post_id)
                .order_by(ScheduledPostImage.position.asc(), ScheduledPostImage.id.asc())
                .all()
            )
            return images

    def get_image_paths(self, post_id: int) -> list[str]:
        images = self.get_images(post_id)
        return [image.image_path for image in images]

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

            (
                session.query(ScheduledPostImage)
                .filter(ScheduledPostImage.scheduled_post_id == post_id)
                .delete(synchronize_session=False)
            )

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
        subreddit: str | None,
        target_type: str,
        scheduled_at_utc: datetime,
        image_paths: list[str] | None = None,
        image_path: str | None = None,
        nsfw: bool = False,
        spoiler: bool = False,
        flair_id: str | None = None,
        flair_text: str | None = None,
        reset_attempts: bool = True,
    ) -> bool:
        with db.SessionLocal() as session:
            post = session.get(ScheduledPost, post_id)

            if post is None:
                return False

            if post.status != "pending":
                return False

            normalized_image_paths = self._normalize_image_paths(
                image_paths=image_paths,
                image_path=image_path,
            )

            self._ensure_legacy_image_attachment(session, post)

            post.title = title
            post.body = body
            post.subreddit = subreddit
            post.target_type = target_type
            post.flair_id = flair_id
            post.flair_text = flair_text
            post.scheduled_at_utc = scheduled_at_utc
            post.nsfw = nsfw
            post.spoiler = spoiler
            post.updated_at_utc = datetime.now(timezone.utc)

            if reset_attempts:
                post.attempts = 0
            post.error_message = None

            self._replace_post_images(
                session=session,
                post=post,
                image_paths=normalized_image_paths,
            )

            session.commit()
            return True

    def get_due_pending_posts(self, now_utc: datetime) -> list[ScheduledPost]:
        with db.SessionLocal() as session:
            due_query = (
                session.query(ScheduledPost)
                .filter(ScheduledPost.status == "pending")
                .filter(ScheduledPost.scheduled_at_utc <= now_utc)
                .order_by(ScheduledPost.scheduled_at_utc.asc())
            )
            posts = due_query.all()

            changed = False
            for post in posts:
                changed = self._ensure_legacy_image_attachment(session, post) or changed

            if changed:
                session.commit()
                posts = due_query.all()

            return posts
