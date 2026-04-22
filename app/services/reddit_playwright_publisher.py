from datetime import datetime
from pathlib import Path
import random
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

class RedditPlaywrightPublisher:
    def __init__(
        self,
        auth_file: str,
        headless: bool = False,
        debug_artifacts_dir: str = "logs/debug",
    ):
        self.auth_file = Path(auth_file)
        self.headless = headless
        self.debug_artifacts_dir = Path(debug_artifacts_dir)

    def _save_debug_artifacts(self, page, prefix: str) -> None:
        """Save screenshot and HTML page source for debugging purposes."""
        self.debug_artifacts_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        screenshot_path = self.debug_artifacts_dir / f"{prefix}_{timestamp}.png"
        html_path = self.debug_artifacts_dir / f"{prefix}_{timestamp}.html"

        try:
            page.screenshot(path=str(screenshot_path), full_page=True)
            print(f"Debug screenshot saved to: {screenshot_path}")
        except Exception as ex:
            print(f"Could not save screenshot: {ex}")

        try:
            html_path.write_text(page.content(), encoding="utf-8")
            print(f"Debug HTML saved to: {html_path}")
        except Exception as ex:
            print(f"Could not save HTML dump: {ex}")

    def _handle_protection_page(self, page, max_retries: int = 3) -> None:
        """
        Detect simple Reddit / Cloudflare protection pages and try to bypass them
        by refreshing the page a few times.
        """
        for attempt in range(1, max_retries + 1):
            content = page.content()

            if (
                "Prove your humanity" in content
                or "You've been blocked by network security" in content
                or "blocked by network security" in content
            ):
                print(f"Protection page detected (attempt {attempt}/{max_retries}). Refreshing page...")
                page.reload(wait_until="domcontentloaded")
                page.wait_for_timeout(3000 + random.randint(500, 1500))
            else:
                return

        self._save_debug_artifacts(page, "protection_page")
        raise RuntimeError("Protection page still present after refresh retries.")

    def publish(
        self,
        subreddit: str,
        title: str,
        body: str | None = None,
        image_paths: list[str] | None = None,
    ) -> str:
        # Validate auth file
        if not self.auth_file.exists():
            raise RuntimeError("Playwright authentication file not found.")

        # Validate required inputs
        if not subreddit.strip():
            raise RuntimeError("Subreddit cannot be empty.")

        if not title.strip():
            raise RuntimeError("Title cannot be empty.")

        resolved_image_paths: list[Path] = []
        for image_path in image_paths or []:
            if not image_path:
                continue

            resolved_image_path = Path(image_path).resolve()
            if not resolved_image_path.exists():
                raise RuntimeError(f"Image file not found: {resolved_image_path}")

            resolved_image_paths.append(resolved_image_path)

        submit_url = f"https://www.reddit.com/r/{subreddit}/submit"

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(
                    headless=self.headless,
                    args=["--disable-blink-features=AutomationControlled"],
                )

                context = browser.new_context(
                    storage_state=str(self.auth_file),
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/122.0.0.0 Safari/537.36"
                    ),
                )

                page = context.new_page()

                try:
                    print(f"Opening submit page: {submit_url}")
                    page.goto(submit_url, wait_until="domcontentloaded")
                    page.wait_for_timeout(3000 + random.randint(500, 1500))

                    # Handle Reddit / Cloudflare protection pages if they appear
                    self._handle_protection_page(page)

                    # If an image is provided, try to switch to the Images tab first.
                    # Some subreddits require using the Images composer explicitly,
                    # while others do not expose this tab at all.
                    if resolved_image_paths:
                        try:
                            images_tab = page.get_by_role("tab", name="Images").first
                            if images_tab.is_visible():
                                print("Switching to Images tab...")
                                images_tab.click()
                                page.wait_for_timeout(1500)
                        except Exception:
                            print("Images tab not available. Continuing with default composer...")

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
                    if resolved_image_paths:
                        print(f"Uploading {len(resolved_image_paths)} image(s)...")
                        upload_button = page.locator('#device-upload-button:visible').first
                        upload_button.wait_for(state="visible", timeout=10000)

                        with page.expect_file_chooser() as fc_info:
                            upload_button.click()

                        file_chooser = fc_info.value
                        file_chooser.set_files([str(path) for path in resolved_image_paths])

                        print("Waiting for image processing...")
                        page.wait_for_timeout(8000 + max(0, len(resolved_image_paths) - 1) * 2500)

                    # Submit post
                    print("Submitting post...")
                    post_button = page.get_by_role("button", name="Post").first
                    post_button.wait_for(state="visible", timeout=10000)

                    if not post_button.is_enabled():
                        self._save_debug_artifacts(page, "post_button_disabled")
                        raise RuntimeError("Post button is not enabled.")

                    post_button.click()

                    # Wait for redirect / success
                    page.wait_for_timeout(5000)
                    final_url = page.url

                    print(f"Post published successfully: {final_url}")
                    return final_url

                except PlaywrightTimeoutError as ex:
                    self._save_debug_artifacts(page, "timeout_error")
                    raise RuntimeError("Error interacting with Reddit UI.") from ex

                except Exception:
                    self._save_debug_artifacts(page, "unexpected_error")
                    raise

                finally:
                    browser.close()

        except Exception:
            raise
