"""Получение данных о лимите claude.ai из скрытого окна webview.

Мы не вытаскиваем и не расшифровываем cookie браузера. Вместо этого держим
собственное окно webview с реальной сессией claude.ai (человек один раз
входит в него как в обычном браузере), а запрос к /usage API выполняется
JS-кодом ВНУТРИ этого окна через fetch(..., {credentials: 'include'}) — то
есть ровно так же, как это делает браузерное расширение.

Результат fetch кладётся в переменную окна и забирается опросом: так мы не
зависим от того, умеет ли конкретный движок webview дожидаться промисов в
evaluate_js.
"""
import json
import re
import threading
import time
from typing import Any, Dict, Optional

RESULT_VAR = "__clb_result"
HOME_URL = "https://claude.ai/"
LOGIN_URL = "https://claude.ai/login"
FREE_RESET_PATH = "/settings/usage"

# Эвристика поиска кнопки "Reset for free" / "Сбросить бесплатно" на странице
# настроек claude.ai. Сам /usage API (см. fetch_usage) её не отдаёт — это
# отдельная акция в интерфейсе (см. support.claude.com статью "What is a
# limit reset"), поэтому ищем характерную фразу прямо в HTML страницы
# настроек. Если вёрстка claude.ai изменится — просто перестанем находить
# кнопку (кнопка в оверлее тихо не появится), а не упадём.
_FREE_RESET_PATTERN = re.compile(
    r"reset[\s_-]*for[\s_-]*free|free[\s_-]*reset|сброс[а-яё]*\s*бесплатно|бесплатн[а-яё]*\s*сброс",
    re.IGNORECASE,
)


def contains_free_reset_offer(html: Optional[str]) -> bool:
    """Чистая функция: есть ли в переданном HTML признак доступного
    бесплатного сброса лимита. Отдельно от сети/webview — чтобы покрыть
    тестами без них."""
    return bool(html) and bool(_FREE_RESET_PATTERN.search(html))


def build_fetch_js(path: str) -> str:
    """JS, который запускает fetch и кладёт итог (JSON) в window.__clb_result."""
    return f"""
(function () {{
  window.{RESULT_VAR} = null;
  fetch({json.dumps(path)}, {{ credentials: 'include' }})
    .then(function (r) {{
      if (!r.ok) {{ return {{ ok: false, error: 'http_' + r.status }}; }}
      return r.json().then(function (d) {{ return {{ ok: true, data: d }}; }});
    }})
    .catch(function (e) {{ return {{ ok: false, error: String(e) }}; }})
    .then(function (res) {{ window.{RESULT_VAR} = res; }});
  return true;
}})()
"""


def build_text_fetch_js(path: str) -> str:
    """Как build_fetch_js, но забирает текст страницы, а не JSON — нужно,
    чтобы заглянуть в HTML /settings/usage и поискать там кнопку бесплатного
    сброса."""
    return f"""
(function () {{
  window.{RESULT_VAR} = null;
  fetch({json.dumps(path)}, {{ credentials: 'include' }})
    .then(function (r) {{
      if (!r.ok) {{ return {{ ok: false, error: 'http_' + r.status }}; }}
      return r.text().then(function (t) {{ return {{ ok: true, data: t }}; }});
    }})
    .catch(function (e) {{ return {{ ok: false, error: String(e) }}; }})
    .then(function (res) {{ window.{RESULT_VAR} = res; }});
  return true;
}})()
"""


def parse_last_active_org(cookie_string: Optional[str]) -> Optional[str]:
    """Достаёт lastActiveOrg из строки document.cookie (как делает bar.js)."""
    if not cookie_string:
        return None
    for part in cookie_string.split(";"):
        name, _, value = part.strip().partition("=")
        if name == "lastActiveOrg" and value:
            from urllib.parse import unquote

            return unquote(value)
    return None


class ClaudeUsageClient:
    """Опрашивает usage API claude.ai изнутри уже авторизованного окна webview."""

    def __init__(
        self,
        window,
        poll_interval: float = 0.25,
        call_timeout: float = 15.0,
        eval_timeout: float = 5.0,
    ):
        self.window = window
        self.poll_interval = poll_interval
        self.call_timeout = call_timeout
        self.eval_timeout = eval_timeout
        self._org_id: Optional[str] = None

    # ---- низкоуровневое -------------------------------------------------
    def _eval(self, script: str) -> Any:
        """Вызывает window.evaluate_js в отдельном потоке с жёстким тайм-аутом.

        На некоторых системах/бэкендах evaluate_js может не вернуть управление
        ВООБЩЕ НИКОГДА (замеченное поведение: подвисание веб-движка при
        обращении к скрытому/ещё не отрисованному окну). Обычный try/except
        тут не спасает — исключения не будет, поток просто навсегда
        останется внутри вызова. Поэтому ждём результат из отдельного потока
        с join(timeout): если не дождались — возвращаем None и идём дальше,
        а подвисший поток молча доживает в фоне (daemon) сам по себе.
        """
        box: Dict[str, Any] = {}

        def run() -> None:
            try:
                box["value"] = self.window.evaluate_js(script)
            except Exception:
                box["value"] = None

        t = threading.Thread(target=run, daemon=True)
        t.start()
        t.join(self.eval_timeout)
        if t.is_alive():
            return None
        return box.get("value")

    def _on_claude(self) -> bool:
        host = self._eval("location.hostname")
        return isinstance(host, str) and (host == "claude.ai" or host.endswith(".claude.ai"))

    def _call(self, path: str, builder=build_fetch_js) -> Optional[Dict[str, Any]]:
        """GET path внутри окна. Возвращает {'ok': bool, 'data'|'error': ...} или None."""
        if not self._on_claude():
            return None
        if self._eval(builder(path)) is None:
            return None
        deadline = time.monotonic() + self.call_timeout
        while time.monotonic() < deadline:
            res = self._eval(f"window.{RESULT_VAR}")
            if isinstance(res, dict):
                return res
            time.sleep(self.poll_interval)
        return None

    # ---- публичный интерфейс --------------------------------------------
    def is_logged_in(self) -> bool:
        res = self._call("/api/organizations")
        return bool(res and res.get("ok") and isinstance(res.get("data"), list) and res["data"])

    def show_login(self) -> None:
        self.window.load_url(LOGIN_URL)
        self.window.show()

    def hide(self) -> None:
        self.window.hide()

    def _ensure_org(self) -> Optional[str]:
        if self._org_id:
            return self._org_id
        org = parse_last_active_org(self._eval("document.cookie"))
        if not org:
            res = self._call("/api/organizations")
            if res and res.get("ok") and isinstance(res.get("data"), list) and res["data"]:
                org = res["data"][0].get("uuid")
        self._org_id = org
        return org

    def fetch_usage(self) -> Optional[Dict[str, Any]]:
        org_id = self._ensure_org()
        if not org_id:
            return None
        res = self._call(f"/api/organizations/{org_id}/usage")
        if not res or not res.get("ok"):
            # Сессия протухла или организация сменилась — определим заново в следующий раз.
            self._org_id = None
            return None
        data = res.get("data")
        return data if isinstance(data, dict) else None

    def fetch_free_reset_available(self) -> bool:
        """Проверяет, предлагает ли claude.ai сейчас бесплатный сброс лимита
        (кнопка "Reset for free" / "Сбросить бесплатно" на /settings/usage).
        При любой ошибке/разлогине — просто False, не бросает исключений."""
        if not self._ensure_org():
            return False
        res = self._call(FREE_RESET_PATH, builder=build_text_fetch_js)
        if not res or not res.get("ok"):
            return False
        return contains_free_reset_offer(res.get("data"))
