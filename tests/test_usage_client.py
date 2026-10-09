import re

from app import usage_client
from app.usage_client import ClaudeUsageClient, build_fetch_js, parse_last_active_org


class FakeWindow:
    """Имитирует окно webview: понимает наши JS-вызовы и отвечает по сценарию."""

    def __init__(self, responses, hostname="claude.ai", cookie="", polls_before_ready=2):
        self.responses = responses  # path -> {'ok':..., ...}
        self.hostname = hostname
        self.cookie = cookie
        self.polls_before_ready = polls_before_ready
        self._result = None
        self._pending = None
        self._polls = 0
        self.fetched = []
        self.calls = []

    def evaluate_js(self, script):
        s = script.strip()
        if s == "location.hostname":
            return self.hostname
        if s == "document.cookie":
            return self.cookie
        if s.startswith("(function"):
            m = re.search(r'fetch\("([^"]+)"', s)
            path = m.group(1)
            self.fetched.append(path)
            self._pending = self.responses.get(path, {"ok": False, "error": "http_404"})
            self._polls = 0
            return True
        if s == f"window.{usage_client.RESULT_VAR}":
            self._polls += 1
            return self._pending if self._polls > self.polls_before_ready else None
        raise AssertionError("unexpected js: " + s)

    def load_url(self, url):
        self.calls.append(("load_url", url))

    def show(self):
        self.calls.append(("show",))

    def hide(self):
        self.calls.append(("hide",))


def client(win, **kw):
    return ClaudeUsageClient(win, poll_interval=0, call_timeout=1.0, **kw)


def test_build_fetch_js_escapes_path_and_uses_credentials():
    js = build_fetch_js('/api/x"y')
    assert 'fetch("/api/x\\"y"' in js
    assert "credentials: 'include'" in js


def test_parse_last_active_org():
    assert parse_last_active_org("a=1; lastActiveOrg=abc-123; b=2") == "abc-123"
    assert parse_last_active_org("lastActiveOrg=a%2Fb") == "a/b"
    assert parse_last_active_org("a=1") is None
    assert parse_last_active_org("") is None
    assert parse_last_active_org(None) is None


def test_is_logged_in_true_waits_for_result():
    w = FakeWindow({"/api/organizations": {"ok": True, "data": [{"uuid": "o1"}]}})
    assert client(w).is_logged_in() is True
    assert w._polls >= 3  # реально ждал, а не взял первое попавшееся


def test_is_logged_in_false_on_401():
    w = FakeWindow({"/api/organizations": {"ok": False, "error": "http_401"}})
    assert client(w).is_logged_in() is False


def test_is_logged_in_false_on_empty_org_list():
    w = FakeWindow({"/api/organizations": {"ok": True, "data": []}})
    assert client(w).is_logged_in() is False


def test_not_on_claude_host_means_not_logged_in_and_no_fetch():
    w = FakeWindow({}, hostname="accounts.google.com")
    assert client(w).is_logged_in() is False
    assert w.fetched == []


def test_lookalike_host_is_rejected():
    w = FakeWindow({}, hostname="evilclaude.ai")
    assert client(w).is_logged_in() is False
    assert w.fetched == []


def test_fetch_usage_uses_cookie_org_without_listing_orgs():
    data = {"five_hour": {"utilization": 10, "resets_at": None}}
    w = FakeWindow(
        {"/api/organizations/org-9/usage": {"ok": True, "data": data}},
        cookie="lastActiveOrg=org-9",
    )
    assert client(w).fetch_usage() == data
    assert w.fetched == ["/api/organizations/org-9/usage"]


def test_fetch_usage_falls_back_to_first_org():
    data = {"seven_day": {"utilization": 5, "resets_at": None}}
    w = FakeWindow(
        {
            "/api/organizations": {"ok": True, "data": [{"uuid": "first"}, {"uuid": "second"}]},
            "/api/organizations/first/usage": {"ok": True, "data": data},
        }
    )
    assert client(w).fetch_usage() == data
    assert w.fetched == ["/api/organizations", "/api/organizations/first/usage"]


def test_fetch_usage_error_resets_org_and_returns_none():
    w = FakeWindow(
        {"/api/organizations/o/usage": {"ok": False, "error": "http_403"}},
        cookie="lastActiveOrg=o",
    )
    c = client(w)
    assert c.fetch_usage() is None
    assert c._org_id is None  # в следующий раз определим заново


def test_fetch_usage_non_dict_payload_is_none():
    w = FakeWindow(
        {"/api/organizations/o/usage": {"ok": True, "data": [1, 2]}}, cookie="lastActiveOrg=o"
    )
    assert client(w).fetch_usage() is None


def test_timeout_returns_none():
    w = FakeWindow(
        {"/api/organizations": {"ok": True, "data": [{"uuid": "o"}]}}, polls_before_ready=10**9
    )
    c = ClaudeUsageClient(w, poll_interval=0.01, call_timeout=0.05)
    assert c.is_logged_in() is False


def test_evaluate_js_exceptions_are_swallowed():
    class Boom:
        def evaluate_js(self, s):
            raise RuntimeError("navigating")

    assert ClaudeUsageClient(Boom(), poll_interval=0, call_timeout=0.05).fetch_usage() is None


def test_contains_free_reset_offer_english():
    assert usage_client.contains_free_reset_offer("<button>Reset for free</button>") is True


def test_contains_free_reset_offer_russian():
    assert usage_client.contains_free_reset_offer("<button>Сбросить бесплатно</button>") is True
    assert usage_client.contains_free_reset_offer("доступен бесплатный сброс лимита") is True


def test_contains_free_reset_offer_absent():
    assert usage_client.contains_free_reset_offer("<p>ничего особенного тут нет</p>") is False
    assert usage_client.contains_free_reset_offer("") is False
    assert usage_client.contains_free_reset_offer(None) is False


def test_fetch_free_reset_available_true_when_offer_present():
    w = FakeWindow(
        {
            "/api/organizations": {"ok": True, "data": [{"uuid": "o1"}]},
            "/settings/usage": {"ok": True, "data": "<html><button>Reset for free</button></html>"},
        }
    )
    assert client(w).fetch_free_reset_available() is True


def test_fetch_free_reset_available_false_without_offer():
    w = FakeWindow(
        {
            "/api/organizations": {"ok": True, "data": [{"uuid": "o1"}]},
            "/settings/usage": {"ok": True, "data": "<html>ничего</html>"},
        }
    )
    assert client(w).fetch_free_reset_available() is False


def test_fetch_free_reset_available_false_when_logged_out():
    w = FakeWindow({"/api/organizations": {"ok": True, "data": []}})
    assert client(w).fetch_free_reset_available() is False


def test_show_login_and_hide():
    w = FakeWindow({})
    c = client(w)
    c.show_login()
    c.hide()
    assert w.calls == [("load_url", usage_client.LOGIN_URL), ("show",), ("hide",)]
