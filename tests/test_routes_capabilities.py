import json
from io import BytesIO
from pathlib import Path
import unittest
from unittest.mock import patch

from flask import Flask

from app.config import Config
from app.services.reddit_composer_capabilities_service import ComposerCapabilities, FlairOption
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
    def __init__(self):
        self.raise_error = False
        self.last_target_type = None
        self.last_subreddit = None
        self.response = ComposerCapabilities(
            target_type="subreddit",
            subreddit="python",
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

    def inspect(self, target_type: str, subreddit: str | None = None):
        self.last_target_type = target_type
        self.last_subreddit = subreddit
        if self.raise_error:
            raise RuntimeError("boom")
        return self.response


class FakeRepo:
    created_payloads: list[dict] = []

    def create(self, **kwargs):
        self.__class__.created_payloads.append(kwargs)
        return {"id": 1}


class RouteCapabilitiesTests(unittest.TestCase):
    def setUp(self):
        self.config_patch = patch.object(Config, "LOGIN_ENABLED", False)
        self.config_patch.start()

        template_dir = Path(__file__).resolve().parents[1] / "app" / "web" / "templates"
        app = Flask(__name__, template_folder=str(template_dir))
        app.config["TESTING"] = True
        app.config["SECRET_KEY"] = "test-secret"

        self.stub_capabilities = StubCapabilitiesService()
        register_routes(
            app=app,
            file_storage_service=DummyFileStorageService(),
            reddit_publisher=DummyPublisher(),
            composer_capabilities_service=self.stub_capabilities,
        )
        self.client = app.test_client()

    def tearDown(self):
        self.config_patch.stop()

    def _capabilities_json(self) -> str:
        return json.dumps(self.stub_capabilities.response.to_dict())

    def test_capabilities_endpoint_profile_success(self):
        self.stub_capabilities.response = ComposerCapabilities(
            target_type="profile",
            subreddit=None,
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

        response = self.client.post(
            "/posts/capabilities",
            json={"target_type": "profile", "subreddit": ""},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["target_label"], "Profile")

    def test_capabilities_endpoint_subreddit_required(self):
        response = self.client.post(
            "/posts/capabilities",
            json={"target_type": "subreddit", "subreddit": ""},
        )

        self.assertEqual(response.status_code, 400)
        payload = response.get_json()
        self.assertFalse(payload["ok"])

    def test_create_post_blocks_when_capabilities_missing(self):
        self.stub_capabilities.raise_error = True

        response = self.client.post(
            "/posts",
            data={
                "target_type": "subreddit",
                "subreddit": "python",
                "title": "Hello",
                "body": "",
                "scheduled_at": "2030-01-01T10:00",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            b"You must load destination settings before saving",
            response.data,
        )

    def test_create_post_enforces_single_image_limit(self):
        self.stub_capabilities.response = ComposerCapabilities(
            target_type="subreddit",
            subreddit="python",
            image_required=False,
            max_images=1,
            has_flairs=False,
            has_tags=False,
            flair_required=False,
            flairs=[],
            nsfw_available=False,
            nsfw_forced_on=False,
            spoiler_available=False,
        )

        response = self.client.post(
            "/posts",
            data={
                "target_type": "subreddit",
                "subreddit": "python",
                "title": "Hello",
                "body": "",
                "scheduled_at": "2030-01-01T10:00",
                "capabilities_json": self._capabilities_json(),
                "images": [
                    (BytesIO(b"image-a"), "a.png"),
                    (BytesIO(b"image-b"), "b.png"),
                ],
            },
            content_type="multipart/form-data",
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"only allows one image", response.data)

    def test_create_post_persists_flair_and_forced_nsfw(self):
        self.stub_capabilities.response = ComposerCapabilities(
            target_type="subreddit",
            subreddit="python",
            image_required=False,
            max_images=None,
            has_flairs=True,
            has_tags=True,
            flair_required=True,
            flairs=[
                FlairOption(id="", text="No flair"),
                FlairOption(id="flair-123", text="Announcements"),
            ],
            nsfw_available=True,
            nsfw_forced_on=True,
            spoiler_available=True,
        )

        FakeRepo.created_payloads = []
        with patch("app.web.routes.ScheduledPostRepository", FakeRepo):
            response = self.client.post(
                "/posts",
                data={
                    "target_type": "subreddit",
                "subreddit": "python",
                "title": "Hello",
                "body": "",
                "scheduled_at": "2030-01-01T10:00",
                "capabilities_json": self._capabilities_json(),
                "flair_id": "flair-123",
                "spoiler": "1",
            },
            )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(FakeRepo.created_payloads), 1)
        payload = FakeRepo.created_payloads[0]
        self.assertEqual(payload["target_type"], "subreddit")
        self.assertEqual(payload["subreddit"], "python")
        self.assertEqual(payload["flair_id"], "flair-123")
        self.assertEqual(payload["flair_text"], "Announcements")
        self.assertTrue(payload["nsfw"])
        self.assertTrue(payload["spoiler"])


if __name__ == "__main__":
    unittest.main()
