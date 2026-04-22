import sys
from app.config import Config
from app.services.reddit_playwright_publisher import RedditPlaywrightPublisher

AUTH_FILE = Config.PLAYWRIGHT_AUTH_FILE

def main():
    if len(sys.argv) < 4:
        raise RuntimeError(
            "Use: python -m app.scripts.reddit_post <subreddit> <title> <body> [image_path1 image_path2 ...]"
        )

    subreddit = sys.argv[1].strip()
    title = sys.argv[2].strip()
    body = sys.argv[3].strip()
    image_paths = [arg.strip() for arg in sys.argv[4:] if arg.strip()]

    publisher = RedditPlaywrightPublisher(
        auth_file=AUTH_FILE,
        headless=Config.PLAYWRIGHT_HEADLESS,
    )
    
    final_url = publisher.publish(
        subreddit=subreddit,
        title=title,
        body=body,
        image_paths=image_paths,
    )

    print(f"Post successfully published: {final_url}")


if __name__ == "__main__":
    main()
