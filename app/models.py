from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime
from app.db import Base


class ScheduledPost(Base):
    __tablename__ = "scheduled_posts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    title: Mapped[str] = mapped_column(String(300), nullable=False)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    subreddit: Mapped[str] = mapped_column(String(100), nullable=False)
    image_path: Mapped[str | None] = mapped_column(String(500), nullable=True)

    scheduled_at_utc: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    timezone: Mapped[str] = mapped_column(String(100), nullable=False, default="Europe/Madrid")

    status: Mapped[str] = mapped_column(String(50), nullable=False, default="pending")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)

    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    reddit_post_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    reddit_post_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    nsfw: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    spoiler: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    created_at_utc: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    updated_at_utc: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    published_at_utc: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class ScheduledPostImage(Base):
    __tablename__ = "scheduled_post_images"
    __table_args__ = (
        Index(
            "ix_scheduled_post_images_post_id_position",
            "scheduled_post_id",
            "position",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scheduled_post_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("scheduled_posts.id"),
        nullable=False,
    )
    image_path: Mapped[str] = mapped_column(String(500), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at_utc: Mapped[datetime] = mapped_column(DateTime, nullable=False)
