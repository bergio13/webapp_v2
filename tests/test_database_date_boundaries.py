from datetime import datetime as RealDateTime
from types import SimpleNamespace


class RecordingQuery:
    def __init__(self):
        self.gte_calls = []
        self.lt_calls = []

    def select(self, *args, **kwargs):
        return self

    def eq(self, *args, **kwargs):
        return self

    def gte(self, field, value):
        self.gte_calls.append((field, value))
        return self

    def lt(self, field, value):
        self.lt_calls.append((field, value))
        return self

    def order(self, *args, **kwargs):
        return self

    def execute(self):
        return SimpleNamespace(data=[])


class RecordingClient:
    def __init__(self):
        self.last_query = None

    def table(self, _table_name):
        self.last_query = RecordingQuery()
        return self.last_query


class JanuaryDateTime(RealDateTime):
    @classmethod
    def now(cls, tz=None):
        return cls(2026, 1, 15)


def test_get_monthly_movies_uses_exact_next_month_boundary(monkeypatch):
    import database

    fake_client = RecordingClient()
    monkeypatch.setattr(database, "client", fake_client)

    current_year = database.datetime.now().year
    database.get_monthly_movies(parent_id=1, month=2)

    assert ("v_date", f"{current_year}-02-01") in fake_client.last_query.gte_calls
    assert ("v_date", f"{current_year}-03-01") in fake_client.last_query.lt_calls


def test_get_monthly_movies_wraps_december_to_next_year(monkeypatch):
    import database

    fake_client = RecordingClient()
    monkeypatch.setattr(database, "client", fake_client)

    current_year = database.datetime.now().year
    database.get_monthly_movies(parent_id=1, month=12)

    assert ("v_date", f"{current_year}-12-01") in fake_client.last_query.gte_calls
    assert ("v_date", f"{current_year + 1}-01-01") in fake_client.last_query.lt_calls


def test_get_highest_rating_handles_january_rollover(monkeypatch):
    import database

    fake_client = RecordingClient()
    monkeypatch.setattr(database, "client", fake_client)
    monkeypatch.setattr(database, "datetime", JanuaryDateTime)

    database.get_highest_rating()

    assert ("v_date", "2025-12-01") in fake_client.last_query.gte_calls
    assert ("v_date", "2026-02-01") in fake_client.last_query.lt_calls
