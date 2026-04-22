from datetime import datetime, timezone
import hmac
from pathlib import Path
from urllib.parse import urlparse

from flask import abort, current_app, redirect, render_template, request, send_from_directory, session, url_for
from app.config import Config
from app.repositories.scheduled_post_repository import ScheduledPostRepository
from app.services.validation_service import PostValidationService


def register_routes(app, file_storage_service, reddit_publisher):
    validation_service = PostValidationService()
    allowed_status_values = ("pending", "publishing", "posted", "failed", "cancelled")
    allowed_status_set = set(allowed_status_values)
    allowed_sort_fields = ("id", "title", "subreddit", "status", "scheduled_at_utc")
    allowed_sort_set = set(allowed_sort_fields)
    allowed_sort_directions = {"asc", "desc"}

    def _image_filename(image_path: str | None) -> str | None:
        if not image_path:
            return None
        return Path(image_path).name

    def _scheduled_at_form_value(scheduled_at_utc) -> str:
        if scheduled_at_utc is None:
            return ""

        if scheduled_at_utc.tzinfo is None:
            scheduled_at_utc = scheduled_at_utc.replace(tzinfo=timezone.utc)

        return scheduled_at_utc.astimezone().strftime("%Y-%m-%dT%H:%M")

    def _build_form_data_from_post(post) -> dict:
        return {
            "title": post.title or "",
            "body": post.body or "",
            "subreddit": post.subreddit or "",
            "scheduled_at": _scheduled_at_form_value(post.scheduled_at_utc),
        }

    def _render_edit_template(post, form_data: dict, errors: list[str], existing_images: list[dict]):
        return render_template(
            "edit_post.html",
            errors=errors,
            form_data=form_data,
            post=post,
            existing_images=existing_images,
        )

    def _is_safe_next_url(next_url: str) -> bool:
        if not next_url:
            return False

        parsed = urlparse(next_url)
        if parsed.scheme or parsed.netloc:
            return False

        return next_url.startswith("/") and not next_url.startswith("//")

    def _build_login_redirect_target() -> str:
        if request.query_string:
            return request.full_path
        return request.path

    def _parse_local_datetime_to_utc(raw_value: str) -> datetime | None:
        if not raw_value:
            return None

        try:
            parsed_local = datetime.fromisoformat(raw_value)
        except ValueError:
            return None

        if parsed_local.tzinfo is None:
            local_timezone = datetime.now().astimezone().tzinfo
            if local_timezone is None:
                return None
            parsed_local = parsed_local.replace(tzinfo=local_timezone)

        return parsed_local.astimezone(timezone.utc)

    def _parse_csv_tokens(raw_value: str) -> list[str]:
        return [token.strip() for token in raw_value.split(",") if token.strip()]

    def _get_uploaded_images() -> list:
        images = [file for file in request.files.getlist("images") if file and file.filename]
        if images:
            return images

        legacy_image = request.files.get("image")
        if legacy_image and legacy_image.filename:
            return [legacy_image]

        return []

    def _build_new_image_file_pairs(uploaded_images: list, requested_keys: list[str]) -> list[tuple[str, object]]:
        valid_requested_keys = [key for key in requested_keys if key.startswith("new:")]
        keys_are_valid = (
            len(valid_requested_keys) == len(uploaded_images)
            and len(set(valid_requested_keys)) == len(valid_requested_keys)
        )

        if not keys_are_valid:
            valid_requested_keys = [f"new:{index}" for index, _ in enumerate(uploaded_images)]

        return list(zip(valid_requested_keys, uploaded_images))

    def _build_post_images_view_data(repo: ScheduledPostRepository, post_id: int) -> list[dict]:
        images = repo.get_images(post_id)
        items: list[dict] = []
        for image in images:
            filename = _image_filename(image.image_path)
            if not filename:
                continue

            items.append(
                {
                    "id": image.id,
                    "image_path": image.image_path,
                    "filename": filename,
                    "url": url_for("uploaded_file", filename=filename),
                    "position": image.position,
                }
            )

        return items

    def _delete_images_with_warning(paths: list[str], post_id: int, action: str) -> None:
        for path in set(paths):
            try:
                file_storage_service.delete_image(path)
            except (OSError, ValueError) as ex:
                current_app.logger.warning(
                    "Could not %s image for post ID=%s: %s",
                    action,
                    post_id,
                    ex,
                )

    @app.before_request
    def require_access_code():
        if not Config.LOGIN_ENABLED:
            return None

        if request.endpoint in {"login", "static"}:
            return None

        if session.get("access_granted") is True:
            return None

        return redirect(url_for("login", next=_build_login_redirect_target()))

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if not Config.LOGIN_ENABLED:
            return redirect(url_for("home"))

        if session.get("access_granted") is True:
            return redirect(url_for("home"))

        next_url = request.values.get("next", "")

        if request.method == "POST":
            submitted_password = request.form.get("password", "")
            if hmac.compare_digest(submitted_password, Config.LOGIN_PASSWORD):
                session.clear()
                session["access_granted"] = True

                if _is_safe_next_url(next_url):
                    return redirect(next_url)

                return redirect(url_for("home"))

            return render_template(
                "login.html",
                error="Invalid access code.",
                next_url=next_url if _is_safe_next_url(next_url) else "",
            )

        return render_template(
            "login.html",
            error=None,
            next_url=next_url if _is_safe_next_url(next_url) else "",
        )

    @app.route("/logout", methods=["POST"])
    def logout():
        session.clear()
        if Config.LOGIN_ENABLED:
            return redirect(url_for("login"))
        return redirect(url_for("home"))

    @app.route("/")
    def home():
        q = request.args.get("q", "").strip()

        status = request.args.get("status", "").strip().lower()
        if status not in allowed_status_set:
            status = ""

        scheduled_from = request.args.get("scheduled_from", "").strip()
        scheduled_to = request.args.get("scheduled_to", "").strip()
        scheduled_from_utc = _parse_local_datetime_to_utc(scheduled_from)
        scheduled_to_utc = _parse_local_datetime_to_utc(scheduled_to)

        if scheduled_from and scheduled_from_utc is None:
            scheduled_from = ""
        if scheduled_to and scheduled_to_utc is None:
            scheduled_to = ""

        sort_by = request.args.get("sort_by", "id").strip()
        if sort_by not in allowed_sort_set:
            sort_by = "id"

        sort_dir = request.args.get("sort_dir", "desc").strip().lower()
        if sort_dir not in allowed_sort_directions:
            sort_dir = "desc"

        repo = ScheduledPostRepository()
        posts = repo.get_all(
            q=q or None,
            status=status or None,
            scheduled_from_utc=scheduled_from_utc,
            scheduled_to_utc=scheduled_to_utc,
            sort_by=sort_by,
            sort_dir=sort_dir,
        )

        base_params = {
            "q": q,
            "status": status,
            "scheduled_from": scheduled_from,
            "scheduled_to": scheduled_to,
        }

        sort_links: dict[str, str] = {}
        for column in allowed_sort_fields:
            next_dir = "asc"
            if sort_by == column and sort_dir == "asc":
                next_dir = "desc"

            sort_links[column] = url_for(
                "home",
                **base_params,
                sort_by=column,
                sort_dir=next_dir,
            )

        filters = {
            "q": q,
            "status": status,
            "scheduled_from": scheduled_from,
            "scheduled_to": scheduled_to,
            "sort_by": sort_by,
            "sort_dir": sort_dir,
            "is_active": bool(q or status or scheduled_from or scheduled_to),
        }

        return render_template(
            "index.html",
            posts=posts,
            filters=filters,
            sort_links=sort_links,
            status_options=allowed_status_values,
        )

    @app.route("/posts/new")
    def new_post():
        return render_template("create_post.html", errors=[], form_data=None)

    @app.route("/posts", methods=["POST"])
    def create_post():
        title = request.form.get("title", "").strip()
        body = request.form.get("body", "").strip()
        subreddit = request.form.get("subreddit", "").strip()
        scheduled_at_raw = request.form.get("scheduled_at", "").strip()
        uploaded_images = _get_uploaded_images()
        requested_new_image_keys = _parse_csv_tokens(request.form.get("new_image_keys", ""))
        new_image_pairs = _build_new_image_file_pairs(uploaded_images, requested_new_image_keys)
        order_tokens = _parse_csv_tokens(request.form.get("image_order", ""))

        form_data = {
            "title": title,
            "body": body,
            "subreddit": subreddit,
            "scheduled_at": scheduled_at_raw,
        }

        errors, scheduled_at_utc = validation_service.validate_post_form(form_data)

        if errors:
            return render_template("create_post.html", errors=errors, form_data=form_data)

        saved_new_images_by_key: dict[str, str] = {}
        try:
            for image_key, image_file in new_image_pairs:
                saved_new_images_by_key[image_key] = file_storage_service.save_image(image_file)
        except (OSError, ValueError) as ex:
            errors.append(str(ex))

        if errors:
            _delete_images_with_warning(
                list(saved_new_images_by_key.values()),
                post_id=0,
                action="rollback uploaded",
            )
            return render_template("create_post.html", errors=errors, form_data=form_data)

        ordered_image_paths: list[str] = []
        used_new_keys: set[str] = set()

        if order_tokens:
            for token in order_tokens:
                if token in saved_new_images_by_key and token not in used_new_keys:
                    ordered_image_paths.append(saved_new_images_by_key[token])
                    used_new_keys.add(token)

        for image_key, image_path in saved_new_images_by_key.items():
            if image_key not in used_new_keys:
                ordered_image_paths.append(image_path)

        repo = ScheduledPostRepository()
        repo.create(
            title=title,
            body=body or None,
            subreddit=subreddit,
            scheduled_at_utc=scheduled_at_utc,
            image_paths=ordered_image_paths,
        )

        return redirect(url_for("home"))

    @app.route("/posts/<int:post_id>")
    def post_detail(post_id: int):
        repo = ScheduledPostRepository()
        post = repo.get_by_id(post_id)

        if post is None:
            abort(404)

        image_items = _build_post_images_view_data(repo, post_id)
        return render_template(
            "post_detail.html",
            post=post,
            image_items=image_items,
        )

    @app.route("/posts/<int:post_id>/edit")
    def edit_post(post_id: int):
        repo = ScheduledPostRepository()
        post = repo.get_by_id(post_id)

        if post is None:
            abort(404)

        if post.status != "pending":
            abort(400)

        form_data = _build_form_data_from_post(post)
        existing_images = _build_post_images_view_data(repo, post_id)
        return _render_edit_template(post, form_data, errors=[], existing_images=existing_images)

    @app.route("/posts/<int:post_id>/edit", methods=["POST"])
    def update_post(post_id: int):
        repo = ScheduledPostRepository()
        post = repo.get_by_id(post_id)

        if post is None:
            abort(404)

        if post.status != "pending":
            abort(400)

        title = request.form.get("title", "").strip()
        body = request.form.get("body", "").strip()
        subreddit = request.form.get("subreddit", "").strip()
        scheduled_at_raw = request.form.get("scheduled_at", "").strip()
        uploaded_images = _get_uploaded_images()
        requested_new_image_keys = _parse_csv_tokens(request.form.get("new_image_keys", ""))
        new_image_pairs = _build_new_image_file_pairs(uploaded_images, requested_new_image_keys)
        order_tokens = _parse_csv_tokens(request.form.get("image_order", ""))

        existing_images = repo.get_images(post_id)
        existing_key_to_path = {
            f"existing:{image.id}": image.image_path for image in existing_images
        }

        form_data = {
            "title": title,
            "body": body,
            "subreddit": subreddit,
            "scheduled_at": scheduled_at_raw,
        }

        errors, scheduled_at_utc = validation_service.validate_post_form(form_data)

        if errors:
            existing_images_data = _build_post_images_view_data(repo, post_id)
            return _render_edit_template(post, form_data, errors, existing_images_data)

        if scheduled_at_utc is None:
            abort(400)

        saved_new_images_by_key: dict[str, str] = {}
        try:
            for image_key, image_file in new_image_pairs:
                saved_new_images_by_key[image_key] = file_storage_service.save_image(image_file)
        except (OSError, ValueError) as ex:
            errors.append(str(ex))

        if errors:
            _delete_images_with_warning(
                list(saved_new_images_by_key.values()),
                post_id=post_id,
                action="rollback uploaded",
            )
            existing_images_data = _build_post_images_view_data(repo, post_id)
            return _render_edit_template(post, form_data, errors, existing_images_data)

        final_image_paths: list[str] = []
        used_existing_tokens: set[str] = set()
        used_new_tokens: set[str] = set()

        if order_tokens:
            for token in order_tokens:
                if token in existing_key_to_path and token not in used_existing_tokens:
                    final_image_paths.append(existing_key_to_path[token])
                    used_existing_tokens.add(token)
                elif token in saved_new_images_by_key and token not in used_new_tokens:
                    final_image_paths.append(saved_new_images_by_key[token])
                    used_new_tokens.add(token)

            for image_key, image_path in saved_new_images_by_key.items():
                if image_key not in used_new_tokens:
                    final_image_paths.append(image_path)
                    used_new_tokens.add(image_key)
        else:
            for image_key, image_path in existing_key_to_path.items():
                final_image_paths.append(image_path)
                used_existing_tokens.add(image_key)

            for image_key, image_path in saved_new_images_by_key.items():
                final_image_paths.append(image_path)
                used_new_tokens.add(image_key)

        removed_existing_paths = [
            image_path
            for image_key, image_path in existing_key_to_path.items()
            if image_key not in used_existing_tokens
        ]

        updated = repo.update_pending(
            post_id=post_id,
            title=title,
            body=body or None,
            subreddit=subreddit,
            scheduled_at_utc=scheduled_at_utc,
            image_paths=final_image_paths,
            reset_attempts=True,
        )

        if not updated:
            _delete_images_with_warning(
                list(saved_new_images_by_key.values()),
                post_id=post_id,
                action="rollback uploaded",
            )
            abort(400)

        _delete_images_with_warning(
            removed_existing_paths,
            post_id=post_id,
            action="delete removed",
        )

        return redirect(url_for("post_detail", post_id=post_id))

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

    @app.route("/posts/<int:post_id>/publish-now", methods=["POST"])
    def publish_now(post_id: int):
        repo = ScheduledPostRepository()
        post = repo.get_by_id(post_id)

        if post is None:
            abort(404)

        if post.status != "pending":
            abort(400)

        image_paths = repo.get_image_paths(post.id)
        try:
            final_url = reddit_publisher.publish(
                subreddit=post.subreddit,
                title=post.title,
                body=post.body,
                image_paths=image_paths,
            )
            repo.mark_posted(post.id, final_url)
        except Exception as ex:
            repo.mark_failed(post.id, str(ex))

        return redirect(url_for("post_detail", post_id=post_id))

    @app.route("/posts/<int:post_id>/delete", methods=["POST"])
    def delete_post(post_id: int):
        repo = ScheduledPostRepository()
        post = repo.get_by_id(post_id)

        if post is None:
            abort(404)

        if post.status != "cancelled":
            abort(400)

        image_paths = repo.get_image_paths(post_id)

        deleted = repo.delete_cancelled(post_id)
        if not deleted:
            abort(400)

        _delete_images_with_warning(
            image_paths,
            post_id=post_id,
            action="delete",
        )

        return redirect(url_for("home"))
