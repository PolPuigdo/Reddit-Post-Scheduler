from flask import Flask
from app.config import Config

def create_app():
    app = Flask(__name__)

    @app.route("/")
    def home():
        return "Reddit Auto Post está funcionando 🚀"

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(host=Config.APP_HOST, port=Config.APP_PORT, debug=Config.DEBUG)