from flask import Flask
from dotenv import load_dotenv
from pathlib import Path

from .config import Settings
from .db import Database
from .routes import register_routes


def create_app() -> Flask:
    project_root = Path(__file__).resolve().parents[1]
    load_dotenv(project_root / ".env")

    app = Flask(__name__)
    settings = Settings.from_env()
    app.config["DMS_SETTINGS"] = settings
    app.config["DMS_DB"] = Database(settings)
    app.config["SECRET_KEY"] = settings.token_secret

    @app.after_request
    def add_cors_headers(response):
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type,Authorization"
        response.headers["Access-Control-Allow-Methods"] = "GET,POST,PUT,DELETE,OPTIONS"
        return response

    @app.route("/", defaults={"path": ""}, methods=["OPTIONS"])
    @app.route("/<path:path>", methods=["OPTIONS"])
    def options(path):
        return ("", 204)

    register_routes(app)
    return app
