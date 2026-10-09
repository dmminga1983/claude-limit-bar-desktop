"""Определяет, является ли сейчас активным (на переднем плане) окно Claude —
десктоп-приложение Claude или вкладка браузера, открытая на claude.ai. Нужно
для режима оверлея "только при использовании Claude" (app/overlay.py).

Без доступа к содержимому страницы заголовок окна переднего плана — это
единственный переносимый способ отличить "сейчас работаю в Claude" от любого
другого окна. Заголовок окна десктоп-приложения Claude и заголовок вкладки
браузера на claude.ai (название чата или просто "Claude") почти всегда
содержат слово "Claude" — на этом эвристика и строится.
"""
import ctypes
import logging
import traceback

log = logging.getLogger("claude_limit_bar")

_user32 = None


def _get_user32():
    global _user32
    if _user32 is None:
        _user32 = ctypes.WinDLL("user32", use_last_error=True)
    return _user32


def foreground_window_title() -> str:
    """Заголовок окна, которое сейчас активно (на переднем плане). Пустая
    строка, если прочитать не удалось (не Windows, ошибка WinAPI и т.п.) —
    вызывающий код в таком случае просто не считает Claude активным."""
    try:
        user32 = _get_user32()
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return ""
        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return ""
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        return buf.value or ""
    except Exception:
        log.error("foreground: failed to read window title:\n%s", traceback.format_exc())
        return ""


def claude_is_foreground(title: str = None) -> bool:
    """True, если заголовок активного сейчас окна похож на Claude (десктоп-
    приложение или вкладка браузера на claude.ai). Можно передать заголовок
    напрямую (для тестов) — без аргумента читает его сам."""
    if title is None:
        title = foreground_window_title()
    return "claude" in title.lower()
