from datetime import datetime, timezone

from flask import Flask

from app.config import Config
from app.db import Base, init_db
import app.models
from app.repositories.scheduled_post_repository import ScheduledPostRepository


def create_app():
    app = Flask(__name__)

    engine = init_db(Config.DATABASE_URL)
    Base.metadata.create_all(bind=engine)

    @app.route("/")
    def home():
        repo = ScheduledPostRepository()
        posts = repo.get_all()

        if not posts:
            demo_post = repo.create(
                title="Mi primer post programado",
                subreddit="test",
                scheduled_at_utc=datetime.now(timezone.utc),
                body="Este es un post de prueba guardado en SQLite"
            )
            posts = [demo_post]

        lines = []
        for post in posts:
            lines.append(
                f"ID: {post.id} | Title: {post.title} | Subreddit: {post.subreddit} | Status: {post.status}"
            )

        return "<br>".join(lines)

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(host=Config.APP_HOST, port=Config.APP_PORT, debug=Config.DEBUG)