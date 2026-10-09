"""_snap() не трогает Tk напрямую (только winfo_screenwidth/height), поэтому
проверяем его отдельно, без создания настоящего окна (на CI часто нет дисплея).

Сам модуль app.overlay импортирует tkinter на уровне файла — на машинах без
него (бывает на некоторых Linux-сборках/CI без GUI) этот файл с тестами
пропускается целиком, а не ломает весь прогон pytest.
"""
import pytest

tk = pytest.importorskip("tkinter")

from app.overlay import (  # noqa: E402
    MODE_ALWAYS,
    MODE_CLAUDE_ONLY,
    SNAP_MARGIN,
    WIDTH,
    OverlayWidget,
    _effective_visible,
)


class _FakeRoot:
    def __init__(self, sw, sh):
        self._sw = sw
        self._sh = sh

    def winfo_screenwidth(self):
        return self._sw

    def winfo_screenheight(self):
        return self._sh


def _widget(sw=1920, sh=1080):
    w = OverlayWidget(
        config=None,
        on_hide=lambda: None,
        is_tray_enabled=lambda: True,
        on_toggle_tray=lambda: None,
        on_quit=lambda: None,
    )
    w.root = _FakeRoot(sw, sh)
    return w


def test_snap_left_edge():
    w = _widget()
    assert w._snap(10, 300) == (0, 300)


def test_snap_right_edge():
    w = _widget(sw=1920)
    x, y = w._snap(1920 - WIDTH - 5, 300)
    assert x == 1920 - WIDTH


def test_snap_top_edge():
    w = _widget()
    assert w._snap(300, 5) == (300, 0)


def test_snap_bottom_edge():
    w = _widget(sh=1080)
    # Высота карточки теперь динамическая (подгоняется под содержимое,
    # см. model.content_height) — фиксированной константы HEIGHT больше
    # нет, используем текущую высоту свежесозданного виджета (ещё без
    # данных, т.е. "нет данных").
    x, y = w._snap(300, 1080 - w._height - 5)
    assert y == 1080 - w._height


def test_snap_corner():
    w = _widget(sw=1920, sh=1080)
    assert w._snap(3, 3) == (0, 0)
    x, y = w._snap(1920 - WIDTH - 2, 1080 - w._height - 2)
    assert (x, y) == (1920 - WIDTH, 1080 - w._height)


def test_no_snap_away_from_edges():
    w = _widget()
    assert w._snap(500, 400) == (500, 400)


def test_snap_margin_boundary():
    w = _widget()
    # Ровно на границе притяжения - должно прилипнуть (<=).
    assert w._snap(SNAP_MARGIN, 300) == (0, 300)
    # Чуть дальше - не должно.
    assert w._snap(SNAP_MARGIN + 1, 300) == (SNAP_MARGIN + 1, 300)


# ---- _effective_visible: логика режима "поверх всех окон" vs "только Claude" ----

def test_always_mode_follows_want():
    assert _effective_visible(want=True, mode=MODE_ALWAYS, claude_foreground=False) is True
    assert _effective_visible(want=False, mode=MODE_ALWAYS, claude_foreground=True) is False


def test_claude_only_mode_hides_when_claude_not_foreground():
    assert _effective_visible(want=True, mode=MODE_CLAUDE_ONLY, claude_foreground=False) is False


def test_claude_only_mode_shows_when_claude_foreground():
    assert _effective_visible(want=True, mode=MODE_CLAUDE_ONLY, claude_foreground=True) is True


def test_claude_only_mode_still_respects_overlay_disabled():
    # overlay_enabled=False (want=False) побеждает, даже если Claude активен.
    assert _effective_visible(want=False, mode=MODE_CLAUDE_ONLY, claude_foreground=True) is False


def test_overlay_widget_reads_initial_mode_from_config():
    class _Cfg:
        def get(self, key):
            return {"overlay_mode": "claude_only"}.get(key)

        def set(self, key, value):
            pass

    w = OverlayWidget(
        config=_Cfg(),
        on_hide=lambda: None,
        is_tray_enabled=lambda: True,
        on_toggle_tray=lambda: None,
        on_quit=lambda: None,
    )
    assert w._mode == "claude_only"


def test_overlay_widget_defaults_to_always_without_config():
    w = _widget()
    assert w._mode == MODE_ALWAYS


def test_set_mode_updates_internal_state():
    w = _widget()
    w.set_mode(MODE_CLAUDE_ONLY)
    assert w._mode == MODE_CLAUDE_ONLY
