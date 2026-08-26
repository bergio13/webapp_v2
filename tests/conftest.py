import importlib
from types import SimpleNamespace

import pytest


class FakeQuery:
    def __init__(self, data=None):
        self._data = data or []

    def select(self, *args, **kwargs):
        return self

    def eq(self, *args, **kwargs):
        return self

    def gte(self, *args, **kwargs):
        return self

    def lt(self, *args, **kwargs):
        return self

    def order(self, *args, **kwargs):
        return self

    def insert(self, *args, **kwargs):
        return self

    def update(self, *args, **kwargs):
        return self

    def delete(self, *args, **kwargs):
        return self

    def single(self):
        return self

    def execute(self):
        return SimpleNamespace(data=self._data)


class FakeSupabaseClient:
    def table(self, _table_name):
        return FakeQuery()


@pytest.fixture
def app_module(monkeypatch):
    # Minimal env for importing app/database without real external services.
    monkeypatch.setenv("SUPABASEURL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASEKEY", "test-key")
    monkeypatch.setenv("FLASK_SECRET_KEY", "test-secret")
    monkeypatch.setenv("TMDB_API_KEY", "test-tmdb")
    monkeypatch.setenv("EMAIL_PROVIDER", "gmail")
    monkeypatch.setenv("KINETO_MAIL_PASSWORD", "test-mail-password")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-openrouter-key")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    import supabase

    monkeypatch.setattr(supabase, "create_client", lambda *_args, **_kwargs: FakeSupabaseClient())

    import database

    importlib.reload(database)

    import app as webapp

    importlib.reload(webapp)
    return webapp


@pytest.fixture
def client(app_module):
    app = app_module.app
    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = False
    with app.test_client() as test_client:
        yield test_client
