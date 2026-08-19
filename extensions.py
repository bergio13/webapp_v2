"""Flask extension instances.

Initialised *without* an app so they can be shared across blueprints via the
application-factory pattern.  Call ``ext.init_app(app)`` inside the factory.
"""
from flask_caching import Cache
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_login import LoginManager
from flask_mail import Mail
from flask_wtf.csrf import CSRFProtect

mail = Mail()
cache = Cache()
csrf = CSRFProtect()
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["1000 per day", "150 per hour"],
    storage_uri="memory://",
)
login_manager = LoginManager()
