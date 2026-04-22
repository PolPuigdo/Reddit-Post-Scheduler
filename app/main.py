from flask import Flask
from app.config import Config
from app.db import Base, init_db, run_schema_migrations
import app.models
from app.services.file_storage_service import FileStorageService
from app.services.reddit_playwright_publisher import RedditPlaywrightPublisher
from app.web.routes import register_routes


def create_app():
    Config.ensure_runtime_directories()

    app = Flask(__name__, template_folder="web/templates")
    app.config["MAX_CONTENT_LENGTH"] = Config.MAX_CONTENT_LENGTH
    if Config.SECRET_KEY:
        app.config["SECRET_KEY"] = Config.SECRET_KEY

    engine = init_db(Config.DATABASE_URL)
    Base.metadata.create_all(bind=engine)
    run_schema_migrations()

    file_storage_service = FileStorageService(Config.UPLOAD_FOLDER)
    
    reddit_publisher = RedditPlaywrightPublisher(
        auth_file=Config.PLAYWRIGHT_AUTH_FILE,
        headless=Config.PLAYWRIGHT_HEADLESS,
        debug_artifacts_dir=Config.DEBUG_ARTIFACTS_DIR,
    )

    register_routes(app, file_storage_service, reddit_publisher)

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(host=Config.APP_HOST, port=Config.APP_PORT, debug=Config.DEBUG)
