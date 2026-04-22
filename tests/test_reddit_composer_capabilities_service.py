import unittest

from app.services.reddit_composer_capabilities_service import RedditComposerCapabilitiesService


class RedditComposerCapabilitiesServiceTests(unittest.TestCase):
    def test_detect_max_images_single(self):
        value = RedditComposerCapabilitiesService.detect_max_images(
            "Drag and Drop or upload media Upload files"
        )
        self.assertEqual(value, 1)

    def test_detect_max_images_multiple(self):
        value = RedditComposerCapabilitiesService.detect_max_images(
            "Drag and Drop images or Upload files"
        )
        self.assertIsNone(value)

    def test_detect_flair_and_tags_required(self):
        has_flairs, has_tags, flair_required = RedditComposerCapabilitiesService.detect_flair_tag_state(
            "Add flair and tags *",
            button_disabled=False,
        )
        self.assertTrue(has_flairs)
        self.assertTrue(has_tags)
        self.assertTrue(flair_required)

    def test_detect_tags_only(self):
        has_flairs, has_tags, flair_required = RedditComposerCapabilitiesService.detect_flair_tag_state(
            "Add tags",
            button_disabled=False,
        )
        self.assertFalse(has_flairs)
        self.assertTrue(has_tags)
        self.assertFalse(flair_required)

    def test_detect_flair_disabled_button(self):
        has_flairs, has_tags, flair_required = RedditComposerCapabilitiesService.detect_flair_tag_state(
            "Add tags",
            button_disabled=True,
        )
        self.assertFalse(has_flairs)
        self.assertFalse(has_tags)
        self.assertFalse(flair_required)


if __name__ == "__main__":
    unittest.main()
