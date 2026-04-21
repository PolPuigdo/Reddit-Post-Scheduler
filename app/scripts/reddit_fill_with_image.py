from pathlib import Path
import sys
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright
from app.config import Config

AUTH_FILE = Path(Config.PLAYWRIGHT_AUTH_FILE)

def main():
    if not AUTH_FILE.exists():
        raise RuntimeError("The authentication file does not exist. Run reddit_login first..")

    if len(sys.argv) < 5:
        raise RuntimeError(
            "Use: python -m app.scripts.reddit_fill_with_image <subreddit> <title> <body> <image_path>"
        )

    subreddit = sys.argv[1].strip()
    title = sys.argv[2].strip()
    body = sys.argv[3].strip()
    image_path = Path(sys.argv[4]).resolve()

    if not subreddit:
        raise RuntimeError("The subreddit cannot be empty.")

    if not title:
        raise RuntimeError("The title cannot be left blank.")

    if not image_path.exists():
        raise RuntimeError(f"The image does not exist: {image_path}")

    submit_url = f"https://www.reddit.com/r/{subreddit}/submit"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(storage_state=str(AUTH_FILE))
        page = context.new_page()

        print(f"Opening: {submit_url}")
        page.goto(submit_url, wait_until="domcontentloaded")
        page.wait_for_timeout(3000)

        # Title
        title_input = page.locator('textarea[name="title"]')
        title_input.wait_for(state="visible", timeout=10000)
        title_input.fill(title)

        page.wait_for_timeout(500)

        # Body (optional)
        if body:
            body_input = page.locator(
                'div[name="body"][contenteditable="true"][role="textbox"]:visible'
            ).first
            body_input.wait_for(state="visible", timeout=10000)
            body_input.click()
            body_input.press_sequentially(body)

        page.wait_for_timeout(1000)

        # Upload an image using the visible button in the UI
        print("Uploading image...")

        upload_button = page.locator('#device-upload-button:visible').first
        upload_button.wait_for(state="visible", timeout=10000)

        with page.expect_file_chooser() as fc_info:
            upload_button.click()

        file_chooser = fc_info.value
        file_chooser.set_files(str(image_path))

        print("Image uploaded to the file selector.")

        # Please wait while Reddit processes and displays the preview
        page.wait_for_timeout(8000)

        print("Form submitted. Nothing will be published. Check your browser window.")
        page.wait_for_timeout(15000)

        browser.close()


if __name__ == "__main__":
    try:
        main()
    except PlaywrightTimeoutError as ex:
        raise RuntimeError("Error interacting with the Reddit UI.") from ex