"""Точка входа. Держит одно окно webview с сессией claude.ai (видимое при
старте — пряталось бы, но на некоторых системах это вешает evaluate_js
намертво, см. _background) и из него опрашивает лимит; результат показывают
два независимо включаемых вида: значок в трее (app/tray_icon.py) и плавающее
окошко поверх экрана (app/overlay.py). Логика переключателей — в
app/controller.py.
"""
import logging
import os
import threading
import time
import traceback

import webview

from . import config as config_module
from .controller import Controller
from .overlay import OverlayWidget
from .tray_icon import TrayApp
from .usage_client import ClaudeUsageClient

LOGIN_POLL_SECONDS = 2
FAILS_BEFORE_RELOGIN = 3
LOGIN_WAIT_MAX_CHECKS = 150  # 2 сек * 150 = 5 минут — после этого считаем окно нерабочим
LAUNCH_MAX_ATTEMPTS = 3
RELAUNCH_DELAY_SECONDS = 6

log = logging.getLogger("claude_limit_bar")


def _setup_logging() -> None:
    """Пишет подробный журнал в %APPDATA%\\ClaudeLimitBar\\trace.log, чтобы было
    видно, на каком именно шаге зависает/падает фон, даже если окно консоли
    закрыто или вывод некуда смотреть в моменте."""
    log_dir = config_module.config_dir()
    log_dir.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(log_dir / "trace.log", encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    root.addHandler(handler)
    # Дублируем в консоль (если она есть) — видно сразу при debug_console.bat.
    console = logging.StreamHandler()
    console.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    root.addHandler(console)


def _quit() -> None:
    log.info("quit requested, exiting process")
    os._exit(0)


class WindowDeadError(Exception):
    """Окно webview перестало отвечать (например, закрылось/упало сразу после
    старта — так бывает, если WebView2 ещё не был готов сразу после
    перезагрузки компьютера). Поднимается, чтобы фоновый поток не крутился
    вхолостую вечно, а main() мог пересоздать окно заново."""


def _wait_for_login(client: ClaudeUsageClient) -> None:
    """Показывает окно входа и ждёт, пока пользователь войдёт в claude.ai.

    Если окно перестало отвечать (закрылось само, упало) — не ждём вечно:
    через LOGIN_WAIT_MAX_CHECKS проверок сдаёмся и поднимаем WindowDeadError,
    чтобы main() пересоздал окно заново, а не завис молчаливым «зомби»-потоком.
    """
    log.info("showing login window, waiting for sign-in")
    client.show_login()
    n = 0
    while not client.is_logged_in():
        n += 1
        if n % 5 == 0:
            log.info("still waiting for login (%d checks so far)", n)
        if n >= LOGIN_WAIT_MAX_CHECKS:
            raise WindowDeadError("login window unresponsive for too long")
        time.sleep(LOGIN_POLL_SECONDS)
    log.info("login detected, hiding window")
    client.hide()


def _background(window, cfg: config_module.Config, started_ok: threading.Event) -> None:
    try:
        _background_impl(window, cfg, started_ok)
    except Exception:
        log.error("background thread crashed:\n%s", traceback.format_exc())
        raise


def _background_impl(window, cfg: config_module.Config, started_ok: threading.Event) -> None:
    # Окно создаётся ВИДИМЫМ (см. main()): на некоторых системах evaluate_js на
    # скрытом окне webview блокируется навсегда и не реагирует ни на какие
    # таймауты в нашем коде (весь наш троттлинг обходится синхронным вызовом
    # window.evaluate_js, который просто не возвращает управление). Поэтому
    # никогда не прячем окно, пока не получили от него хотя бы один ответ.
    log.info("background thread started")
    client = ClaudeUsageClient(window)

    log.info("checking is_logged_in()")
    logged_in = client.is_logged_in()
    log.info("is_logged_in() -> %s", logged_in)
    if not logged_in:
        _wait_for_login(client)
    else:
        client.hide()

    log.info("creating tray and overlay")
    holder = {}
    tray = TrayApp(
        is_overlay_enabled=lambda: bool(cfg.get("overlay_enabled")),
        on_toggle_overlay=lambda: holder["c"].toggle_overlay(),
        on_quit=lambda: holder["c"].quit(),
        get_overlay_mode=lambda: holder["c"].get_overlay_mode(),
        on_set_overlay_mode=lambda mode: holder["c"].set_overlay_mode(mode),
    )
    overlay = OverlayWidget(
        cfg,
        on_hide=lambda: holder["c"].set_overlay(False),
        is_tray_enabled=lambda: bool(cfg.get("tray_enabled")),
        on_toggle_tray=lambda: holder["c"].toggle_tray(),
        on_quit=lambda: holder["c"].quit(),
    )
    controller = Controller(cfg, tray, overlay, on_quit=_quit)
    holder["c"] = controller

    log.info("starting overlay Tk thread")
    threading.Thread(target=overlay.run, daemon=True).start()  # один поток Tk на всё время работы
    log.info("calling controller.apply_initial()")
    controller.apply_initial()
    log.info("apply_initial() done, entering polling loop")
    started_ok.set()  # сообщаем main(): окно и трей реально заработали, перезапуск не нужен

    fails = 0
    poll_n = 0
    FREE_RESET_EVERY_N_POLLS = 5  # страница настроек меняется редко — не дёргаем её на каждый тик
    while True:
        data = client.fetch_usage()
        if data is None:
            log.debug("fetch_usage() -> None")
        else:
            # Логируем именно те окна, что попадают в оверлей (model уже
            # отбирает и округляет их) — этого достаточно, чтобы при жалобе
            # "шкала показывает неправильно" сверить с тем, что видно в
            # самом интерфейсе claude.ai, не печатая весь сырой ответ API.
            try:
                from . import model as _model

                log.debug(
                    "fetch_usage() -> %s",
                    [
                        {"key": w["key"], "used": w["used"], "left": w["left"], "reset": w["reset"]}
                        for w in _model.windows_from_data(data)
                    ],
                )
            except Exception:
                log.debug("fetch_usage() -> data (couldn't format windows)")
        controller.push(data)
        if data is None:
            fails += 1
            if fails >= FAILS_BEFORE_RELOGIN and not client.is_logged_in():
                log.info("too many failed polls, re-showing login window")
                _wait_for_login(client)
                fails = 0
        else:
            fails = 0
        if poll_n % FREE_RESET_EVERY_N_POLLS == 0:
            try:
                free_reset = client.fetch_free_reset_available()
            except Exception:
                log.error("fetch_free_reset_available() crashed:\n%s", traceback.format_exc())
                free_reset = False
            log.debug("fetch_free_reset_available() -> %s", free_reset)
            controller.push_free_reset(free_reset)
        poll_n += 1
        time.sleep(max(15, int(cfg.get("poll_seconds") or 60)))


def main() -> None:
    _setup_logging()
    log.info("=== Claude Limit Bar starting ===")
    cfg = config_module.Config()
    storage = config_module.config_dir() / "webview"
    storage.mkdir(parents=True, exist_ok=True)

    # Сразу после перезагрузки компьютера движок WebView2 иногда ещё не готов,
    # и окно webview падает/закрывается в первые секунды — тогда фоновый поток
    # (см. WindowDeadError) просто остался бы крутиться вхолостую вечно, без
    # окна и без трея, и выглядело бы так, будто программа "не запустилась".
    # Поэтому пробуем пересоздать окно ещё пару раз с паузой, если до трея
    # дело так и не дошло.
    for attempt in range(1, LAUNCH_MAX_ATTEMPTS + 1):
        log.info("launch attempt %d/%d", attempt, LAUNCH_MAX_ATTEMPTS)
        started_ok = threading.Event()
        start_ts = time.monotonic()
        window = webview.create_window(
            "Claude — вход", "https://claude.ai/", hidden=False, width=480, height=700
        )
        # private_mode=False + storage_path — чтобы вход в claude.ai сохранялся между запусками.
        webview.start(_background, (window, cfg, started_ok), private_mode=False, storage_path=str(storage))
        elapsed = time.monotonic() - start_ts
        log.info(
            "webview.start() returned after %.1fs (attempt %d, started_ok=%s)",
            elapsed, attempt, started_ok.is_set(),
        )
        if started_ok.is_set():
            # Трей/оверлей хоть раз да заработали — окно закрылось штатно
            # (пользователь выбрал "Выход" и т.п.), повторный запуск не нужен.
            break
        if attempt < LAUNCH_MAX_ATTEMPTS:
            log.info("window died before tray started — retrying in %ds", RELAUNCH_DELAY_SECONDS)
            time.sleep(RELAUNCH_DELAY_SECONDS)
        else:
            log.error("gave up after %d attempts — window never became usable", LAUNCH_MAX_ATTEMPTS)

    # Гарантируем, что процесс действительно завершится, а не "зависнет"
    # незаметным для диспетчера задач потоком.
    os._exit(0)


if __name__ == "__main__":
    main()
