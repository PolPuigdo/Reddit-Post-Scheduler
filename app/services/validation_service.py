from datetime import datetime, timezone


class PostValidationService:
    def validate_create_post_form(self, form_data: dict) -> tuple[list[str], datetime | None]:
        title = form_data.get("title", "").strip()
        subreddit = form_data.get("subreddit", "").strip()
        scheduled_at_raw = form_data.get("scheduled_at", "").strip()

        errors: list[str] = []
        scheduled_at_utc: datetime | None = None

        if not title:
            errors.append("El título es obligatorio.")

        if not subreddit:
            errors.append("El subreddit es obligatorio.")
        elif " " in subreddit:
            errors.append("El subreddit no debe contener espacios.")

        if not scheduled_at_raw:
            errors.append("La fecha y hora son obligatorias.")

        if scheduled_at_raw:
            try:
                local_dt = datetime.strptime(scheduled_at_raw, "%Y-%m-%dT%H:%M")
                scheduled_at_utc = local_dt.astimezone(timezone.utc)
            except ValueError:
                errors.append("La fecha y hora tienen un formato inválido.")

        return errors, scheduled_at_utc