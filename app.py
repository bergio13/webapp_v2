"""Application entry point.

Creates and configures the Flask application via the factory function
``create_app()``.  Extensions are initialised here so they are bound to the
correct app instance before any blueprint or request handler runs.
"""
import os

from dotenv import load_dotenv

# Load .env *before* any module that reads os.environ (e.g. database, config).
load_dotenv()

# Polyfill pkgutil.get_loader for Python 3.14+ compatibility with Flask 2.x
import importlib.util
import pkgutil

if not hasattr(pkgutil, "get_loader"):
    def _get_loader(name):
        try:
            spec = importlib.util.find_spec(name)
            return spec.loader if spec else None
        except (ValueError, AttributeError, ImportError):
            return None
    pkgutil.get_loader = _get_loader

from flask import Flask
from flask_login import current_user

from auth.auth import auth
from auth.models import User
from auth.restore import restore
from config import Config
from database import get_user_by_id
from extensions import cache, csrf, limiter, login_manager, mail
from routes.analytics import analytics_bp
from routes.main import main_bp
from routes.movies import movies_bp
from routes.profile import profile_bp
from routes.social import social_bp
from routes.watchlist import watchlist_bp
import requests
from ai_helpers import (
    OPENROUTER_API_URL,
    OPENROUTER_MODEL_ID,
    OPENROUTER_MODEL_FALLBACKS,
    OPENROUTER_REQUEST_TIMEOUT,
    OPENROUTER_TOTAL_TIMEOUT,
    OPENROUTER_MODEL_DEADLINE,
    OPENROUTER_MAX_ATTEMPTS,
    get_ai_movie_recommendation,
    format_ai_response_to_html,
)
from utils import (
    get_user_watch_history_summary,
    get_watched_title_year_lookup,
)


def create_app(config_class=Config) -> Flask:
    """Application factory."""
    app = Flask(__name__)
    app.config.from_object(config_class)

    # ----------------------------------------------------------------
    # Initialise extensions
    # ----------------------------------------------------------------
    mail.init_app(app)
    cache.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)
    login_manager.init_app(app)

    # ----------------------------------------------------------------
    # Flask-Login configuration
    # ----------------------------------------------------------------
    login_manager.login_view = "auth.login"
    login_manager.login_message = "Please log in to access this page"
    login_manager.login_message_category = "error"

    @login_manager.user_loader
    def load_user(user_id):
        users = get_user_by_id(user_id)
        if users:
            d = users[0]
            return User(id=d["id"], username=d["username"], email=d["email"])
        return None

    # ----------------------------------------------------------------
    # Register blueprints
    # ----------------------------------------------------------------
    app.register_blueprint(auth)
    app.register_blueprint(restore)
    app.register_blueprint(main_bp)
    app.register_blueprint(analytics_bp)
    app.register_blueprint(profile_bp)
    app.register_blueprint(social_bp)
    app.register_blueprint(movies_bp)
    app.register_blueprint(watchlist_bp)

    # ----------------------------------------------------------------
    # Reverse proxy support (Render, Cloudflare, Nginx)
    # ----------------------------------------------------------------
    from werkzeug.middleware.proxy_fix import ProxyFix
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

    # ----------------------------------------------------------------
    # Start-up diagnostics (info-level, not print)
    # ----------------------------------------------------------------
    app.logger.info("SMTP server    : %s:%s", app.config.get("MAIL_SERVER"), app.config.get("MAIL_PORT"))
    app.logger.info("SMTP user      : %s", app.config.get("MAIL_USERNAME"))
    app.logger.info("Sender         : %s", app.config.get("MAIL_DEFAULT_SENDER"))
    app.logger.info("TLS / SSL      : %s / %s (timeout: %ss)", app.config.get("MAIL_USE_TLS"), app.config.get("MAIL_USE_SSL"), app.config.get("MAIL_TIMEOUT"))

    if not app.config.get("MAIL_PASSWORD"):
        app.logger.warning("KINETO_MAIL_PASSWORD is not set — email delivery will fail")

    return app


# ---------------------------------------------------------------------------
# Module-level app instance (required by gunicorn / flask run)
# ---------------------------------------------------------------------------
app = create_app()

if __name__ == "__main__":
    debug_mode = os.environ.get("FLASK_DEBUG", "1") == "1"
    app.run(debug=debug_mode)