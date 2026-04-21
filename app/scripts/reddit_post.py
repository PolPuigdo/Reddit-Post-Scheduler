import sys
from app.services.reddit_playwright_publisher import RedditPlaywrightPublisher

AUTH_FILE = "playwright/.auth/reddit.json"

def main():
    if len(sys.argv) < 5:
        raise RuntimeError(
            "Use: python -m app.scripts.reddit_post <subreddit> <title> <body> <image_path>"
        )

    subreddit = sys.argv[1].strip()
    title = sys.argv[2].strip()
    body = sys.argv[3].strip()
    image_path = sys.argv[4].strip()

    publisher = RedditPlaywrightPublisher(auth_file=AUTH_FILE)
    final_url = publisher.publish(
        subreddit=subreddit,
        title=title,
        body=body,
        image_path=image_path,
    )

    print(f"Post successfully published: {final_url}")


if __name__ == "__main__":
    main()