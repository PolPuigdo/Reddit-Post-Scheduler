from datetime import datetime, timezone

from flask import Flask, redirect, render_template, request, url_for

from app.config import Config
from app.db import Base, init_db
import app.models
from app.repositories.scheduled_post_repository import ScheduledPostRepository


def create_app():
    app = Flask(__name__, template_folder="web/templates")

    engine = init_db(Config.DATABASE_URL)
    Base.metadata.create_all(bind=engine)

    @app.route("/")
    def home():
        repo = ScheduledPostRepository()
        posts = repo.get_all()
        return render_template("index.html", posts=posts)

    @app.route("/posts/new")
    def new_post():
        return render_template("create_post.html")

    @app.route("/posts", methods=["POST"])
    def create_post():
        title = request.form["title"]
        body = request.form.get("body") or None
        subreddit = request.form["subreddit"]
        scheduled_at_raw = request.form["scheduled_at"]

        local_dt = datetime.strptime(scheduled_at_raw, "%Y-%m-%dT%H:%M")
        scheduled_at_utc = local_dt.astimezone(timezone.utc)

        repo = ScheduledPostRepository()
        repo.create(
            title=title,
            body=body,
            subreddit=subreddit,
            scheduled_at_utc=scheduled_at_utc,
        )

        return redirect(url_for("home"))

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(host=Config.APP_HOST, port=Config.APP_PORT, debug=Config.DEBUG)