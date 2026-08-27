"""Application configuration.

A single flat ``Config`` class loaded via ``app.config.from_object(Config)``.
Mail provider is resolved from the EMAIL_PROVIDER environment variable at
import time so the correct SMTP credentials are always active.
"""
import os


class Config:
    # ------------------------------------------------------------------ core
    SECRET_KEY = os.environ.get("FLASK_SECRET_KEY")

    # ----------------------------------------------------------------- cache
    CACHE_TYPE = "SimpleCache"
    CACHE_DEFAULT_TIMEOUT = 300  # seconds
    SEND_FILE_MAX_AGE_DEFAULT = 86400  # 24 hours for static asset caching

    # ------------------------------------------------------------------ mail
    MAIL_MAX_EMAILS = None
    MAIL_ASCII_ATTACHMENTS = False

    MAIL_SERVER = os.environ.get("MAIL_SERVER", "smtp.gmail.com")
    MAIL_PORT = int(os.environ.get("MAIL_PORT", 587))
    MAIL_USERNAME = os.environ.get("MAIL_USERNAME", "kinetoweb@gmail.com")
    MAIL_PASSWORD = os.environ.get("KINETO_MAIL_PASSWORD") or os.environ.get("MAIL_PASSWORD")
    MAIL_DEFAULT_SENDER = os.environ.get("MAIL_DEFAULT_SENDER", os.environ.get("MAIL_USERNAME", "kinetoweb@gmail.com"))
    MAIL_USE_TLS = os.environ.get("MAIL_USE_TLS", "true").lower() in ("true", "1", "yes")
    MAIL_USE_SSL = os.environ.get("MAIL_USE_SSL", "false").lower() in ("true", "1", "yes")
    MAIL_TIMEOUT = int(os.environ.get("MAIL_TIMEOUT", 20))

    # ------------------------------------------------------------------ urls
    RENDER_EXTERNAL_URL = os.environ.get("RENDER_EXTERNAL_URL")
    BASE_URL = os.environ.get("BASE_URL")
