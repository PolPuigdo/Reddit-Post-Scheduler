from datetime import datetime, timezone

class PostValidationService:
    def validate_create_post_form(self, form_data: dict) -> tuple[list[str], datetime | None]:
        title = form_data.get("title", "").strip()
        subreddit = form_data.get("subreddit", "").strip()
        scheduled_at_raw = form_data.get("scheduled_at", "").strip()

        errors: list[str] = []
        scheduled_at_utc: datetime | None = None

        if not title:
            errors.append("The title is required.")

        if not subreddit:
            errors.append("The subreddit is required.")
        elif " " in subreddit:
            errors.append("The subreddit must not contain spaces.")

        if not scheduled_at_raw:
            errors.append("The date and time are required.")

        if scheduled_at_raw:
            try:
                local_dt = datetime.strptime(scheduled_at_raw, "%Y-%m-%dT%H:%M")
                scheduled_at_utc = local_dt.astimezone(timezone.utc)
            except ValueError:
                errors.append("The date and time are in an invalid format.")

        return errors, scheduled_at_utc