from datetime import datetime, timezone
import hmac
import json
from pathlib import Path
from urllib.parse import urlparse

from flask import abort, current_app, jsonify, redirect, render_template, request, send_from_directory, session, url_for
from app.config import Config
from app.repositories.scheduled_post_repository import ScheduledPostRepository
from app.services.cached_composer_capabilities_service import CachedComposerCapabilitiesService
from app.services.reddit_composer_capabilities_service import RedditComposerCapabilitiesService
from app.services.validation_service import PostValidationService


def register_routes(app, file_storage_service, reddit_publisher, composer_capabilities_service=None):
    validation_service = PostValidationService()
    base_capabilities_service = composer_capabilities_service or RedditComposerCapabilitiesService(
        auth_file=Config.PLAYWRIGHT_AUTH_FILE,
        headless=Config.PLAYWRIGHT_HEADLESS,
        debug_artifacts_dir=Config.DEBUG_ARTIFACTS_DIR,
    )
    capabilities_service = CachedComposerCapabilitiesService(
        base_service=base_capabilities_service,
        ttl_seconds=Config.CAPABILITIES_CACHE_TTL_SECONDS,
    )
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

    def _scheduled_at_local_display_value(scheduled_at_utc) -> str:
        if scheduled_at_utc is None:
            return "-"

        if scheduled_at_utc.tzinfo is None:
            scheduled_at_utc = scheduled_at_utc.replace(tzinfo=timezone.utc)

        return scheduled_at_utc.astimezone().strftime("%Y-%m-%d %H:%M")

    def _build_form_data_from_post(post) -> dict:
        target_type = (post.target_type or "subreddit").strip().lower()
        if target_type not in {"subreddit", "profile"}:
            target_type = "subreddit"

        subreddit_value = (post.subreddit or "").strip() if target_type == "subreddit" else ""

        return {
            "title": post.title or "",
            "body": post.body or "",
            "target_type": target_type,
            "subreddit": subreddit_value,
            "scheduled_at": _scheduled_at_form_value(post.scheduled_at_utc),
            "flair_id": post.flair_id or "",
            "flair_text": post.flair_text or "",
            "nsfw": bool(post.nsfw),
            "spoiler": bool(post.spoiler),
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

    def _parse_bool_from_form(raw_value: str | None) -> bool:
        return (raw_value or "").strip().lower() in {"1", "true", "on", "yes"}

    def _normalize_target_type(raw_target: str | None) -> str:
        target_type = (raw_target or "").strip().lower()
        if target_type in {"subreddit", "profile"}:
            return target_type
        return "subreddit"

    def _target_label(target_type: str, subreddit: str | None) -> str:
        if target_type == "profile":
            return "Profile"
        return f"r/{subreddit}" if subreddit else "r/-"

    def _extract_capabilities_or_none(raw_payload: str | None) -> dict | None:
        if not raw_payload:
            return None
        try:
            payload = json.loads(raw_payload)
        except (TypeError, ValueError):
            return None
        if not isinstance(payload, dict):
            return None
        return payload

    def _load_composer_capabilities(target_type: str, subreddit: str | None) -> tuple[dict | None, str | None]:
        try:
            capabilities = capabilities_service.inspect(target_type=target_type, subreddit=subreddit)
            return capabilities.to_dict(), None
        except Exception as ex:
            current_app.logger.warning(
                "Could not inspect Reddit composer capabilities for target=%s subreddit=%s: %s",
                target_type,
                subreddit,
                ex,
            )
            return None, "Could not read Reddit post settings for this destination. Please try again."

    def _validate_form_against_capabilities(
        capabilities: dict,
        target_type: str,
        uploaded_images_count: int,
        submitted_flair_id: str,
        submitted_nsfw: bool,
        submitted_spoiler: bool,
    ) -> tuple[list[str], str | None, bool, bool]:
        errors: list[str] = []

        image_required = bool(capabilities.get("image_required"))
        max_images = capabilities.get("max_images")
        has_flairs = bool(capabilities.get("has_flairs"))
        has_tags = bool(capabilities.get("has_tags"))
        flair_required = bool(capabilities.get("flair_required"))
        flairs = capabilities.get("flairs") or []
        nsfw_available = bool(capabilities.get("nsfw_available"))
        nsfw_forced_on = bool(capabilities.get("nsfw_forced_on"))
        spoiler_available = bool(capabilities.get("spoiler_available"))

        if image_required and uploaded_images_count == 0:
            errors.append("At least one image is required for this destination.")

        if max_images == 1 and uploaded_images_count > 1:
            errors.append("This destination only allows one image.")

        final_flair_id: str | None = None
        if target_type == "subreddit" and has_flairs:
            valid_flair_ids = {(flair.get("id") or "") for flair in flairs if isinstance(flair, dict)}
            if flair_required and not submitted_flair_id:
                errors.append("A flair is required for this subreddit.")

            if submitted_flair_id or flair_required:
                if submitted_flair_id not in valid_flair_ids:
                    errors.append("Selected flair is no longer valid for this subreddit.")
                else:
                    final_flair_id = submitted_flair_id
            elif submitted_flair_id == "" and "" in valid_flair_ids:
                final_flair_id = ""

        final_nsfw = False
        final_spoiler = False

        if target_type == "subreddit" and has_tags:
            if nsfw_forced_on:
                final_nsfw = True
            elif nsfw_available:
                final_nsfw = submitted_nsfw

            if spoiler_available:
                final_spoiler = submitted_spoiler

        return errors, final_flair_id, final_nsfw, final_spoiler

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
            scheduled_at_local_display=_scheduled_at_local_display_value,
        )

    @app.route("/posts/new")
    def new_post():
        return render_template(
            "create_post.html",
            errors=[],
            form_data={
                "target_type": "subreddit",
                "subreddit": "",
                "title": "",
                "body": "",
                "scheduled_at": "",
                "flair_id": "",
                "flair_text": "",
                "nsfw": False,
                "spoiler": False,
            },
            capabilities=None,
            target_label=None,
        )

    @app.route("/posts/capabilities", methods=["POST"])
    def post_capabilities():
        payload = request.get_json(silent=True) or {}

        target_type = _normalize_target_type(payload.get("target_type"))
        subreddit = (payload.get("subreddit") or "").strip()
        if target_type == "profile":
            subreddit = ""

        if target_type == "subreddit":
            if not subreddit:
                return jsonify({"ok": False, "error": "Subreddit is required."}), 400
            if " " in subreddit:
                return jsonify({"ok": False, "error": "Subreddit must not contain spaces."}), 400

        capabilities, error_message = _load_composer_capabilities(target_type, subreddit or None)
        if capabilities is None:
            return jsonify({"ok": False, "error": error_message}), 502

        return jsonify(
            {
                "ok": True,
                "capabilities": capabilities,
                "target_label": _target_label(target_type, subreddit or None),
            }
        )

    @app.route("/posts", methods=["POST"])
    def create_post():
        title = request.form.get("title", "").strip()
        body = request.form.get("body", "").strip()
        target_type = _normalize_target_type(request.form.get("target_type"))
        subreddit = request.form.get("subreddit", "").strip()
        if target_type == "profile":
            subreddit = ""
        scheduled_at_raw = request.form.get("scheduled_at", "").strip()
        submitted_flair_id = request.form.get("flair_id", "").strip()
        submitted_nsfw = _parse_bool_from_form(request.form.get("nsfw"))
        submitted_spoiler = _parse_bool_from_form(request.form.get("spoiler"))
        capabilities_payload = _extract_capabilities_or_none(request.form.get("capabilities_json"))
        uploaded_images = _get_uploaded_images()
        requested_new_image_keys = _parse_csv_tokens(request.form.get("new_image_keys", ""))
        new_image_pairs = _build_new_image_file_pairs(uploaded_images, requested_new_image_keys)
        order_tokens = _parse_csv_tokens(request.form.get("image_order", ""))

        form_data = {
            "title": title,
            "body": body,
            "target_type": target_type,
            "subreddit": subreddit,
            "scheduled_at": scheduled_at_raw,
            "flair_id": submitted_flair_id,
            "nsfw": submitted_nsfw,
            "spoiler": submitted_spoiler,
        }

        errors, scheduled_at_utc = validation_service.validate_post_form(form_data)

        live_capabilities: dict | None = capabilities_payload
        if not errors and live_capabilities is None:
            errors.append("You must load destination settings before saving.")

        if not errors and live_capabilities is not None:
            capabilities_target = _normalize_target_type(live_capabilities.get("target_type"))
            capabilities_subreddit = (live_capabilities.get("subreddit") or "").strip()
            if capabilities_target != target_type:
                errors.append("Destination settings are out of sync. Reload destination settings and try again.")
            elif target_type == "subreddit" and capabilities_subreddit != subreddit:
                errors.append("Subreddit settings are out of sync. Reload destination settings and try again.")

        final_flair_id: str | None = None
        final_nsfw = False
        final_spoiler = False

        if not errors and live_capabilities is not None:
            capability_errors, final_flair_id, final_nsfw, final_spoiler = _validate_form_against_capabilities(
                capabilities=live_capabilities,
                target_type=target_type,
                uploaded_images_count=len(uploaded_images),
                submitted_flair_id=submitted_flair_id,
                submitted_nsfw=submitted_nsfw,
                submitted_spoiler=submitted_spoiler,
            )
            errors.extend(capability_errors)

        if errors:
            return render_template(
                "create_post.html",
                errors=errors,
                form_data=form_data,
                capabilities=live_capabilities,
                target_label=_target_label(target_type, subreddit or None),
            )

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
                post_id=0,
                action="rollback uploaded",
            )
            return render_template(
                "create_post.html",
                errors=errors,
                form_data=form_data,
                capabilities=live_capabilities,
                target_label=_target_label(target_type, subreddit or None),
            )

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

        flair_text = None
        if live_capabilities and final_flair_id is not None:
            for flair in live_capabilities.get("flairs") or []:
                if not isinstance(flair, dict):
                    continue
                if (flair.get("id") or "") == final_flair_id:
                    flair_text = (flair.get("text") or "").strip() or None
                    break

        repo = ScheduledPostRepository()
        repo.create(
            title=title,
            body=body or None,
            subreddit=subreddit or None,
            target_type=target_type,
            scheduled_at_utc=scheduled_at_utc,
            image_paths=ordered_image_paths,
            flair_id=final_flair_id,
            flair_text=flair_text,
            nsfw=final_nsfw,
            spoiler=final_spoiler,
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
            scheduled_at_local_display=_scheduled_at_local_display_value,
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
        target_type = _normalize_target_type(post.target_type)
        subreddit = (post.subreddit or "").strip() if target_type == "subreddit" else ""
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
            "target_type": target_type,
            "subreddit": subreddit,
            "scheduled_at": scheduled_at_raw,
            "flair_id": post.flair_id or "",
            "flair_text": post.flair_text or "",
            "nsfw": bool(post.nsfw),
            "spoiler": bool(post.spoiler),
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
            target_type=target_type,
            scheduled_at_utc=scheduled_at_utc,
            image_paths=final_image_paths,
            nsfw=bool(post.nsfw),
            spoiler=bool(post.spoiler),
            flair_id=post.flair_id,
            flair_text=post.flair_text,
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
                target_type=post.target_type,
                title=post.title,
                body=post.body,
                image_paths=image_paths,
                flair_id=post.flair_id,
                nsfw=bool(post.nsfw),
                spoiler=bool(post.spoiler),
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

        if post.status not in {"cancelled", "posted", "failed"}:
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
