"""Вариант 1: значок в системном трее с динамической шкалой и всплывающей
подсказкой (стандартный tooltip иконки трея)."""
import threading
from typing import Any, Callable, Dict, List, Optional

import pystray
from PIL import Image, ImageDraw

from . import model


def _hex_to_rgba(h: str):
    h = h.lstrip("#")
    return tuple(int(h[i : i + 2], 16) for i in (0, 2, 4)) + (255,)


def draw_icon(used_values: List[float]) -> Image.Image:
    """Иконка трея: шкала ОСТАТКА лимита по худшему из окон (короче и краснее — хуже)."""
    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    pad = 4
    d.rounded_rectangle([pad, pad, size - pad, size - pad], radius=14, fill=(30, 32, 38, 255))

    if not used_values:
        d.ellipse([size / 2 - 6, size / 2 - 6, size / 2 + 6, size / 2 + 6], fill=(120, 120, 128, 255))
        return img

    worst = max(used_values)
    color = _hex_to_rgba(model.color_for(worst))
    bar_h = 16
    bar_y = (size - bar_h) // 2
    bar_pad = 9
    track_w = size - 2 * bar_pad
    d.rounded_rectangle([bar_pad, bar_y, size - bar_pad, bar_y + bar_h], radius=8, fill=(60, 64, 72, 255))
    left_pct = max(0.0, 100.0 - worst)
    fw = max(bar_h, round(track_w * left_pct / 100))
    d.rounded_rectangle([bar_pad, bar_y, bar_pad + fw, bar_y + bar_h], radius=8, fill=color)
    return img


class TrayApp:
    """Значок в трее + меню. Можно многократно включать/выключать через start()/stop()."""

    def __init__(
        self,
        is_overlay_enabled: Callable[[], bool],
        on_toggle_overlay: Callable[[], None],
        on_quit: Callable[[], None],
        get_overlay_mode: Optional[Callable[[], str]] = None,
        on_set_overlay_mode: Optional[Callable[[str], None]] = None,
    ):
        self._is_overlay_enabled = is_overlay_enabled
        self._on_toggle_overlay = on_toggle_overlay
        self._on_quit = on_quit
        self._get_overlay_mode = get_overlay_mode or (lambda: "always")
        self._on_set_overlay_mode = on_set_overlay_mode or (lambda mode: None)
        self.icon: Optional[pystray.Icon] = None

    def _menu(self) -> pystray.Menu:
        return pystray.Menu(
            pystray.MenuItem(
                "Плавающее окошко поверх экрана",
                lambda icon, item: self._on_toggle_overlay(),
                checked=lambda item: bool(self._is_overlay_enabled()),
            ),
            pystray.MenuItem(
                "Показывать окошко",
                pystray.Menu(
                    pystray.MenuItem(
                        "Поверх всех окон",
                        lambda icon, item: self._on_set_overlay_mode("always"),
                        radio=True,
                        checked=lambda item: self._get_overlay_mode() == "always",
                    ),
                    pystray.MenuItem(
                        "Только при использовании Claude",
                        lambda icon, item: self._on_set_overlay_mode("claude_only"),
                        radio=True,
                        checked=lambda item: self._get_overlay_mode() == "claude_only",
                    ),
                ),
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Выход", lambda icon, item: self._on_quit()),
        )

    def start(self) -> None:
        if self.icon is not None:
            return
        self.icon = pystray.Icon("claude-limit-bar", draw_icon([]), "Лимит Claude", self._menu())
        threading.Thread(target=self.icon.run, daemon=True).start()

    def stop(self) -> None:
        icon, self.icon = self.icon, None
        if icon is not None:
            try:
                icon.visible = False
                icon.stop()
            except Exception:
                pass

    def update(self, data: Optional[Dict[str, Any]]) -> None:
        icon = self.icon
        if icon is None:
            return
        ws = model.windows_from_data(data)
        icon.icon = draw_icon([w["used"] for w in ws])
        icon.title = model.tooltip_text(data)[:127]  # лимит Windows на подсказку — 127 символов
        try:
            icon.update_menu()
        except Exception:
            pass
