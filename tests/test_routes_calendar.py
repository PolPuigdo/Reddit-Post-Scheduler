from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import unittest
from unittest.mock import patch

from flask import Flask

from app.config import Config
from app.services.reddit_composer_capabilities_service import ComposerCapabilities
from app.web.routes import register_routes


class DummyFileStorageService:
    def save_image(self, file):
        return f"/tmp/{file.filename}"

    def delete_image(self, image_path):
        return None


class DummyPublisher:
    def publish(self, **kwargs):
        return "https://reddit.com/fake"


class StubCapabilitiesService:
    def inspect(self, target_type: str, subreddit: str | None = None):
        return ComposerCapabilities(
            target_type=target_type,
            subreddit=subreddit,
            image_required=False,
            max_images=None,
            has_flairs=False,
            has_tags=False,
            flair_required=False,
            flairs=[],
            nsfw_available=False,
            nsfw_forced_on=False,
            spoiler_available=False,
        )


@dataclass
class _CalendarPost:
    id: int
    title: str
    target_type: str
    subreddit: str | None
    status: str
    scheduled_at_utc: datetime


class FakeCalendarRepo:
    return_posts: list[_CalendarPost] = []
    last_from: datetime | None = None
    last_to: datetime | None = None
    last_statuses: tuple[str, ...] | None = None

    def get_calendar_events(self, from_utc, to_utc, statuses):
        self.__class__.last_from = from_utc
        self.__class__.last_to = to_utc
        self.__class__.last_statuses = statuses
        return list(self.__class__.return_posts)


class RouteCalendarTests(unittest.TestCase):
    def setUp(self):
        self.config_patch = patch.object(Config, "LOGIN_ENABLED", False)
        self.config_patch.start()

        template_dir = Path(__file__).resolve().parents[1] / "app" / "web" / "templates"
        app = Flask(__name__, template_folder=str(template_dir))
        app.config["TESTING"] = True
        app.config["SECRET_KEY"] = "test-secret"

        register_routes(
            app=app,
            file_storage_service=DummyFileStorageService(),
            reddit_publisher=DummyPublisher(),
            composer_capabilities_service=StubCapabilitiesService(),
        )
        self.client = app.test_client()

    def tearDown(self):
        self.config_patch.stop()

    def test_calendar_events_success(self):
        FakeCalendarRepo.return_posts = [
            _CalendarPost(
                id=1,
                title="Post A",
                target_type="subreddit",
                subreddit="python",
                status="pending",
                scheduled_at_utc=datetime(2030, 1, 3, 10, 30, tzinfo=timezone.utc),
            ),
            _CalendarPost(
                id=2,
                title="Post B",
                target_type="profile",
                subreddit=None,
                status="posted",
                scheduled_at_utc=datetime(2030, 1, 7, 11, 45, tzinfo=timezone.utc),
            ),
        ]

        with patch("app.web.routes.ScheduledPostRepository", FakeCalendarRepo):
            response = self.client.get(
                "/posts/calendar/events",
                query_string={
                    "from_utc": "2030-01-01T00:00:00Z",
                    "to_utc": "2030-01-31T23:59:59Z",
                },
            )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["ok"])
        self.assertEqual(len(payload["events"]), 2)
        self.assertEqual(payload["events"][0]["title"], "Post A")
        self.assertEqual(payload["events"][0]["target_type"], "subreddit")
        self.assertEqual(payload["events"][0]["subreddit"], "python")
        self.assertEqual(payload["events"][0]["status"], "pending")
        self.assertTrue(payload["events"][0]["scheduled_at_utc"].endswith("Z"))
        self.assertEqual(FakeCalendarRepo.last_statuses, ("pending", "publishing", "posted"))
        self.assertEqual(FakeCalendarRepo.last_from, datetime(2030, 1, 1, 0, 0, tzinfo=timezone.utc))
        self.assertEqual(FakeCalendarRepo.last_to, datetime(2030, 1, 31, 23, 59, 59, tzinfo=timezone.utc))

    def test_calendar_events_invalid_date_returns_400(self):
        response = self.client.get(
            "/posts/calendar/events",
            query_string={
                "from_utc": "invalid-value",
                "to_utc": "2030-01-31T23:59:59Z",
            },
        )

        self.assertEqual(response.status_code, 400)
        payload = response.get_json()
        self.assertFalse(payload["ok"])

    def test_calendar_events_rejects_naive_datetime(self):
        response = self.client.get(
            "/posts/calendar/events",
            query_string={
                "from_utc": "2030-01-01T00:00:00",
                "to_utc": "2030-01-31T23:59:59Z",
            },
        )

        self.assertEqual(response.status_code, 400)
        payload = response.get_json()
        self.assertFalse(payload["ok"])

    def test_calendar_events_invalid_range_returns_400(self):
        response = self.client.get(
            "/posts/calendar/events",
            query_string={
                "from_utc": "2030-02-01T00:00:00Z",
                "to_utc": "2030-01-01T00:00:00Z",
            },
        )

        self.assertEqual(response.status_code, 400)
        payload = response.get_json()
        self.assertFalse(payload["ok"])


if __name__ == "__main__":
    unittest.main()
