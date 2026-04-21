from datetime import datetime, timezone

from flask import Flask, abort, redirect, render_template, request, url_for

from app.config import Config
from app.db import Base, init_db
import app.models
from app.repositories.scheduled_post_repository import ScheduledPostRepository
from app.services.file_storage_service import FileStorageService


def create_app():
    app = Flask(__name__, template_folder="web/templates")
    app.config["MAX_CONTENT_LENGTH"] = Config.MAX_CONTENT_LENGTH

    engine = init_db(Config.DATABASE_URL)
    Base.metadata.create_all(bind=engine)

    file_storage_service = FileStorageService(Config.UPLOAD_FOLDER)

    @app.route("/")
    def home():
        repo = ScheduledPostRepository()
        posts = repo.get_all()
        return render_template("index.html", posts=posts)

    @app.route("/posts/new")
    def new_post():
        return render_template("create_post.html", errors=[], form_data=None)

    @app.route("/posts", methods=["POST"])
    def create_post():
        title = request.form.get("title", "").strip()
        body = request.form.get("body", "").strip()
        subreddit = request.form.get("subreddit", "").strip()
        scheduled_at_raw = request.form.get("scheduled_at", "").strip()
        image = request.files.get("image")

        errors = []

        if not title:
            errors.append("El título es obligatorio.")

        if not subreddit:
            errors.append("El subreddit es obligatorio.")
        elif " " in subreddit:
            errors.append("El subreddit no debe contener espacios.")

        if not scheduled_at_raw:
            errors.append("La fecha y hora son obligatorias.")

        scheduled_at_utc = None

        if scheduled_at_raw:
            try:
                local_dt = datetime.strptime(scheduled_at_raw, "%Y-%m-%dT%H:%M")
                scheduled_at_utc = local_dt.astimezone(timezone.utc)
            except ValueError:
                errors.append("La fecha y hora tienen un formato inválido.")

        image_path = None

        if image and image.filename:
            try:
                image_path = file_storage_service.save_image(image)
            except ValueError as ex:
                errors.append(str(ex))

        if errors:
            form_data = {
                "title": title,
                "body": body,
                "subreddit": subreddit,
                "scheduled_at": scheduled_at_raw,
            }
            return render_template("create_post.html", errors=errors, form_data=form_data)

        repo = ScheduledPostRepository()
        repo.create(
            title=title,
            body=body or None,
            subreddit=subreddit,
            scheduled_at_utc=scheduled_at_utc,
            image_path=image_path,
        )

        return redirect(url_for("home"))

    @app.route("/posts/<int:post_id>")
    def post_detail(post_id: int):
        repo = ScheduledPostRepository()
        post = repo.get_by_id(post_id)

        if post is None:
            abort(404)

        return render_template("post_detail.html", post=post)

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(host=Config.APP_HOST, port=Config.APP_PORT, debug=Config.DEBUG)