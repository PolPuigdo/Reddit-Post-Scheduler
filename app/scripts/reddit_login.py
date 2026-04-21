from pathlib import Path
from playwright.sync_api import sync_playwright

AUTH_DIR = Path("playwright/.auth")
AUTH_FILE = AUTH_DIR / "reddit.json"

def main():
    AUTH_DIR.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()

        page.goto("https://www.reddit.com/login/", wait_until="domcontentloaded")

        print()
        print("Log in to Reddit manually in your browser window.")
        print("Once you're logged in to Reddit, press ENTER here.")
        input()

        context.storage_state(path=str(AUTH_FILE))
        browser.close()

        print(f"Session state saved in: {AUTH_FILE}")


if __name__ == "__main__":
    main()