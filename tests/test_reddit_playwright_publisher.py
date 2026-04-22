from pathlib import Path
import unittest
from unittest.mock import patch

from app.services.reddit_playwright_publisher import RedditPlaywrightPublisher


class FakeLocator:
    def __init__(self, visible=True, enabled=True):
        self.visible = visible
        self.enabled = enabled
        self.click_count = 0

    @property
    def first(self):
        return self

    def is_visible(self):
        return self.visible

    def wait_for(self, **kwargs):
        return None

    def fill(self, value):
        return None

    def press_sequentially(self, value):
        return None

    def click(self):
        self.click_count += 1

    def is_enabled(self):
        return self.enabled

    def count(self):
        return 1

    def get_attribute(self, name):
        return None

    def is_disabled(self):
        return False


class FakeKeyboard:
    def press(self, key):
        return None


class FakePage:
    def __init__(self):
        self.goto_url = None
        self.url = "https://www.reddit.com/fake-post"
        self.keyboard = FakeKeyboard()

    def goto(self, url, **kwargs):
        self.goto_url = url

    def wait_for_timeout(self, timeout):
        return None

    def content(self):
        return "<html></html>"

    def locator(self, selector):
        if selector == 'textarea[name="title"]':
            return FakeLocator()
        if selector == 'div[name="body"][contenteditable="true"][role="textbox"]:visible':
            return FakeLocator()
        if selector == '#device-upload-button:visible':
            return FakeLocator()
        return FakeLocator()

    def get_by_role(self, role, name=None):
        return FakeLocator()

    def expect_file_chooser(self):
        raise AssertionError("File chooser should not be used in this test.")


class FakeContext:
    def __init__(self, page):
        self.page = page

    def new_page(self):
        return self.page


class FakeBrowser:
    def __init__(self, page):
        self.page = page

    def new_context(self, **kwargs):
        return FakeContext(self.page)

    def close(self):
        return None


class FakeChromium:
    def __init__(self, page):
        self.page = page

    def launch(self, **kwargs):
        return FakeBrowser(self.page)


class FakePlaywrightRuntime:
    def __init__(self, page):
        self.chromium = FakeChromium(page)


class FakePlaywrightContextManager:
    def __init__(self, page):
        self.page = page

    def __enter__(self):
        return FakePlaywrightRuntime(self.page)

    def __exit__(self, exc_type, exc_val, exc_tb):
        return False


class RedditPlaywrightPublisherTests(unittest.TestCase):
    def _create_auth_file(self) -> Path:
        auth_file = Path(__file__).resolve().parent / ".auth_test.json"
        auth_file.write_text("{}", encoding="utf-8")
        self.addCleanup(lambda: auth_file.unlink(missing_ok=True))
        return auth_file

    def test_publish_profile_uses_generic_submit_url(self):
        auth_file = self._create_auth_file()

        page = FakePage()
        publisher = RedditPlaywrightPublisher(auth_file=str(auth_file), headless=True)
        publisher._handle_protection_page = lambda page: None

        with patch("app.services.reddit_playwright_publisher.sync_playwright", return_value=FakePlaywrightContextManager(page)):
            with patch.object(publisher, "_apply_subreddit_options") as apply_options_mock:
                final_url = publisher.publish(
                    target_type="profile",
                    subreddit=None,
                    title="Profile post",
                    body=None,
                    image_paths=[],
                )

        self.assertEqual(final_url, "https://www.reddit.com/fake-post")
        self.assertEqual(page.goto_url, "https://www.reddit.com/submit")
        apply_options_mock.assert_not_called()

    def test_publish_subreddit_uses_subreddit_submit_url_and_applies_options(self):
        auth_file = self._create_auth_file()

        page = FakePage()
        publisher = RedditPlaywrightPublisher(auth_file=str(auth_file), headless=True)
        publisher._handle_protection_page = lambda page: None

        with patch("app.services.reddit_playwright_publisher.sync_playwright", return_value=FakePlaywrightContextManager(page)):
            with patch.object(publisher, "_apply_subreddit_options") as apply_options_mock:
                publisher.publish(
                    target_type="subreddit",
                    subreddit="python",
                    title="Subreddit post",
                    body=None,
                    image_paths=[],
                    flair_id="flair-1",
                    nsfw=True,
                    spoiler=True,
                )

        self.assertEqual(page.goto_url, "https://www.reddit.com/r/python/submit")
        apply_options_mock.assert_called_once()


if __name__ == "__main__":
    unittest.main()
