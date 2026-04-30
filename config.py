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

    # ------------------------------------------------------------------ mail
    MAIL_MAX_EMAILS = None
    MAIL_ASCII_ATTACHMENTS = False

    _EMAIL_PROVIDER = os.environ.get("EMAIL_PROVIDER", "gmail")

    if _EMAIL_PROVIDER == "sendgrid":
        MAIL_SERVER = "smtp.sendgrid.net"
        MAIL_PORT = 587
        MAIL_USERNAME = "apikey"          # literal string required by SendGrid
        MAIL_PASSWORD = os.environ.get("SENDGRID_API_KEY")
        MAIL_USE_TLS = True
        MAIL_USE_SSL = False
        MAIL_DEFAULT_SENDER = "kinetowebapp@gmail.com"
        MAIL_TIMEOUT = 10
    else:
        MAIL_SERVER = "smtp.gmail.com"
        MAIL_PORT = 587
        MAIL_USERNAME = "kinetowebapp@gmail.com"
        MAIL_PASSWORD = os.environ.get("KINETO_MAIL_PASSWORD")
        MAIL_USE_TLS = True
        MAIL_USE_SSL = False
        MAIL_DEFAULT_SENDER = "kinetowebapp@gmail.com"
        MAIL_TIMEOUT = 30
