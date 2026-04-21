from pathlib import Path
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

class RedditPlaywrightPublisher:
    def __init__(self, auth_file: str):
        self.auth_file = Path(auth_file)

    def publish(
        self,
        subreddit: str,
        title: str,
        body: str | None = None,
        image_path: str | None = None,
    ) -> str:
        if not self.auth_file.exists():
            raise RuntimeError("The Playwright authentication file does not exist.")

        if not subreddit.strip():
            raise RuntimeError("The subreddit cannot be empty.")

        if not title.strip():
            raise RuntimeError("The title cannot be left blank.")

        resolved_image_path = None
        if image_path:
            resolved_image_path = Path(image_path).resolve()
            if not resolved_image_path.exists():
                raise RuntimeError(f"No existe la imagen: {resolved_image_path}")

        submit_url = f"https://www.reddit.com/r/{subreddit}/submit"

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=False)
                context = browser.new_context(storage_state=str(self.auth_file))
                page = context.new_page()

                page.goto(submit_url, wait_until="domcontentloaded")
                page.wait_for_timeout(3000)

                # Title
                title_input = page.locator('textarea[name="title"]')
                title_input.wait_for(state="visible", timeout=10000)
                title_input.fill(title)

                # Body (optional)
                if body:
                    body_input = page.locator(
                        'div[name="body"][contenteditable="true"][role="textbox"]:visible'
                    ).first
                    body_input.wait_for(state="visible", timeout=10000)
                    body_input.click()
                    body_input.press_sequentially(body)

                # Image (optional)
                if resolved_image_path:
                    upload_button = page.locator('#device-upload-button:visible').first
                    upload_button.wait_for(state="visible", timeout=10000)

                    with page.expect_file_chooser() as fc_info:
                        upload_button.click()

                    file_chooser = fc_info.value
                    file_chooser.set_files(str(resolved_image_path))

                    page.wait_for_timeout(8000)

                # Post Button
                post_button = page.get_by_role("button", name="Post").first
                post_button.wait_for(state="visible", timeout=10000)

                if not post_button.is_enabled():
                    raise RuntimeError("Post button not enabled.")

                post_button.click()

                page.wait_for_timeout(5000)
                final_url = page.url

                browser.close()

                return final_url

        except PlaywrightTimeoutError as ex:
            raise RuntimeError("Error interacting with the Reddit UI.") from ex