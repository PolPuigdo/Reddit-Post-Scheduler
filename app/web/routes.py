from pathlib import Path
from flask import abort, redirect, render_template, request, send_from_directory, url_for
from app.config import Config
from app.repositories.scheduled_post_repository import ScheduledPostRepository
from app.services.validation_service import PostValidationService


def register_routes(app, file_storage_service):
    validation_service = PostValidationService()
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

        form_data = {
            "title": title,
            "body": body,
            "subreddit": subreddit,
            "scheduled_at": scheduled_at_raw,
        }

        errors, scheduled_at_utc = validation_service.validate_create_post_form(form_data)

        image_path = None

        if image and image.filename:
            try:
                image_path = file_storage_service.save_image(image)
            except ValueError as ex:
                errors.append(str(ex))

        if errors:
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

        image_filename = None
        if post.image_path:
            image_filename = Path(post.image_path).name

        return render_template(
            "post_detail.html",
            post=post,
            image_filename=image_filename
        )

    @app.route("/uploads/<path:filename>")
    def uploaded_file(filename: str):
        return send_from_directory(Config.UPLOAD_FOLDER, filename)
    
    @app.route("/posts/<int:post_id>/cancel", methods=["POST"])
    def cancel_post(post_id: int):
        repo = ScheduledPostRepository()
        cancelled = repo.cancel(post_id)

        if not cancelled:
            abort(404)

        return redirect(url_for("post_detail", post_id=post_id))