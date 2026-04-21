from pathlib import Path
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

class RedditPlaywrightPublisher:
    def __init__(self, auth_file: str, headless: bool = False):
        self.auth_file = Path(auth_file)
        self.headless = headless

    def publish(
        self,
        subreddit: str,
        title: str,
        body: str | None = None,
        image_path: str | None = None,
    ) -> str:
        # Validate auth file
        if not self.auth_file.exists():
            raise RuntimeError("Playwright authentication file not found.")

        # Validate required inputs
        if not subreddit.strip():
            raise RuntimeError("Subreddit cannot be empty.")

        if not title.strip():
            raise RuntimeError("Title cannot be empty.")

        # Resolve image path if provided
        resolved_image_path = None
        if image_path:
            resolved_image_path = Path(image_path).resolve()
            if not resolved_image_path.exists():
                raise RuntimeError(f"Image file not found: {resolved_image_path}")

        submit_url = f"https://www.reddit.com/r/{subreddit}/submit"

        try:
            with sync_playwright() as p:
                # Launch browser (headless configurable)
                browser = p.chromium.launch(headless=self.headless)
                context = browser.new_context(storage_state=str(self.auth_file))
                page = context.new_page()

                print(f"Opening submit page: {submit_url}")
                page.goto(submit_url, wait_until="domcontentloaded")
                page.wait_for_timeout(3000)

                # Fill title
                print("Filling title...")
                title_input = page.locator('textarea[name="title"]')
                title_input.wait_for(state="visible", timeout=10000)
                title_input.fill(title)

                # Fill body if provided
                if body:
                    print("Filling body...")
                    body_input = page.locator(
                        'div[name="body"][contenteditable="true"][role="textbox"]:visible'
                    ).first
                    body_input.wait_for(state="visible", timeout=10000)
                    body_input.click()
                    body_input.press_sequentially(body)

                # Upload image if provided
                if resolved_image_path:
                    print("Uploading image...")
                    upload_button = page.locator('#device-upload-button:visible').first
                    upload_button.wait_for(state="visible", timeout=10000)

                    with page.expect_file_chooser() as fc_info:
                        upload_button.click()

                    file_chooser = fc_info.value
                    file_chooser.set_files(str(resolved_image_path))

                    print("Waiting for image processing...")
                    page.wait_for_timeout(8000)

                # Submit post
                print("Submitting post...")
                post_button = page.get_by_role("button", name="Post").first
                post_button.wait_for(state="visible", timeout=10000)

                if not post_button.is_enabled():
                    raise RuntimeError("Post button is not enabled.")

                post_button.click()

                # Wait for redirect / success
                page.wait_for_timeout(5000)
                final_url = page.url

                print(f"Post published successfully: {final_url}")

                browser.close()

                return final_url

        except PlaywrightTimeoutError as ex:
            raise RuntimeError("Error interacting with Reddit UI.") from ex