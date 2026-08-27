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

    EMAIL_PROVIDER = os.environ.get("EMAIL_PROVIDER", "gmail").strip().lower()
    RESEND_API_KEY = os.environ.get("RESEND_API_KEY")
    SENDGRID_API_KEY = os.environ.get("SENDGRID_API_KEY")

    # Base provider defaults
    if EMAIL_PROVIDER == "resend":
        _default_server = "smtp.resend.com"
        _default_port = 587
        _default_user = "resend"
        _default_pass = os.environ.get("RESEND_API_KEY")
        _default_sender = os.environ.get("MAIL_DEFAULT_SENDER", "onboarding@resend.dev")
        _default_timeout = 10
    elif EMAIL_PROVIDER == "sendgrid":
        _default_server = "smtp.sendgrid.net"
        _default_port = 587
        _default_user = "apikey"
        _default_pass = os.environ.get("SENDGRID_API_KEY")
        _default_sender = os.environ.get("MAIL_DEFAULT_SENDER", "kinetowebapp@gmail.com")
        _default_timeout = 10
    elif EMAIL_PROVIDER == "brevo":
        _default_server = "smtp-relay.brevo.com"
        _default_port = 587
        _default_user = os.environ.get("BREVO_SMTP_LOGIN") or os.environ.get("MAIL_USERNAME")
        _default_pass = os.environ.get("BREVO_API_KEY") or os.environ.get("BREVO_SMTP_KEY") or os.environ.get("MAIL_PASSWORD")
        _default_sender = os.environ.get("MAIL_DEFAULT_SENDER", "kinetowebapp@gmail.com")
        _default_timeout = 10
    else:  # gmail or standard smtp
        _default_server = "smtp.gmail.com"
        _default_port = 587
        _default_user = os.environ.get("MAIL_USERNAME", "kinetowebapp@gmail.com")
        _default_pass = os.environ.get("KINETO_MAIL_PASSWORD") or os.environ.get("MAIL_PASSWORD")
        _default_sender = os.environ.get("MAIL_DEFAULT_SENDER", "kinetowebapp@gmail.com")
        _default_timeout = 20

    # Allow explicit environment variable overrides
    MAIL_SERVER = os.environ.get("MAIL_SERVER", _default_server)
    MAIL_PORT = int(os.environ.get("MAIL_PORT", _default_port))
    MAIL_USERNAME = os.environ.get("MAIL_USERNAME", _default_user)
    MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD", _default_pass)
    MAIL_USE_TLS = os.environ.get("MAIL_USE_TLS", "true").lower() in ("true", "1", "yes")
    MAIL_USE_SSL = os.environ.get("MAIL_USE_SSL", "false").lower() in ("true", "1", "yes")
    MAIL_DEFAULT_SENDER = os.environ.get("MAIL_DEFAULT_SENDER", _default_sender)
    MAIL_TIMEOUT = int(os.environ.get("MAIL_TIMEOUT", _default_timeout))

    # ------------------------------------------------------------------ urls
    RENDER_EXTERNAL_URL = os.environ.get("RENDER_EXTERNAL_URL")
    BASE_URL = os.environ.get("BASE_URL")
