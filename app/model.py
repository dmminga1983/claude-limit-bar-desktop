"""Чистая логика расчёта шкал лимита — без GUI-зависимостей, чтобы её можно
было покрыть тестами. Повторяет то, что делает bar.js в браузерном
расширении, только на Python.
"""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, TypedDict

LABELS: Dict[str, tuple] = {
    "five_hour": ("5ч", "5 часов"),
    "seven_day": ("нед", "неделя"),
    "seven_day_sonnet": ("нед S", "неделя Sonnet"),
    "seven_day_opus": ("нед O", "неделя Opus"),
}

# Порядок, в котором проверяем окна лимита — совпадает с bar.js.
ORDER = ["five_hour", "seven_day", "seven_day_sonnet", "seven_day_opus"]

# Геометрия компактной карточки (без зависимости от tkinter, чтобы отдельно
# проверять тестами) — используется app/overlay.py для расчёта высоты окна
# и положения подписи процента вдоль шкалы.
LAYOUT_PAD = 8        # внутренний отступ сверху/снизу карточки
LAYOUT_BAR_H = 12     # высота строки со шкалой и подписью слева (сужена с 14 — проценты остаются читаемыми)
LAYOUT_ROW_GAP = 6    # зазор между строками-окнами лимита
LAYOUT_RESET_H = 12   # высота строки "сброс через ..."
LAYOUT_BTN_GAP = 4    # зазор перед кнопкой "Бесплатный сброс"
LAYOUT_BTN_H = 16     # высота кнопки "Бесплатный сброс"
LAYOUT_NO_DATA_H = 20  # высота строки "нет данных"

_LABEL_MARGIN = 3  # отступ подписи процента от края шкалы/заливки


def color_for(used: float) -> str:
    """Цвет шкалы по проценту ИСПОЛЬЗОВАНИЯ (0-100)."""
    if used >= 80:
        return "#ff5c5c"
    if used >= 50:
        return "#f5c542"
    return "#4cd17a"


def until_reset(iso: Optional[str], now: Optional[datetime] = None) -> str:
    """Человекочитаемое 'сброс через ...' из ISO-времени сброса лимита."""
    if not iso:
        return ""
    now = now or datetime.now(timezone.utc)
    try:
        reset_at = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return ""
    delta = reset_at - now
    total_minutes = round(delta.total_seconds() / 60)
    if total_minutes <= 0:
        return ""
    days, rem = divmod(total_minutes, 1440)
    hours, minutes = divmod(rem, 60)
    if days > 0:
        return f"сброс через {days} д {hours} ч"
    if hours > 0:
        return f"сброс через {hours} ч {minutes} мин"
    return f"сброс через {minutes} мин"


class Window(TypedDict):
    key: str
    used: float
    left: int
    reset: str


def windows_from_data(
    data: Optional[Dict[str, Any]], now: Optional[datetime] = None
) -> List[Window]:
    """Превращает сырой ответ /usage API в список окон лимита для отрисовки."""
    if not data:
        return []
    out: List[Window] = []
    for key in ORDER:
        w = data.get(key)
        if not w or w.get("utilization") is None:
            continue
        used = max(0.0, min(100.0, float(w.get("utilization") or 0)))
        out.append(
            {
                "key": key,
                "used": used,
                "left": round(100 - used),
                "reset": until_reset(w.get("resets_at"), now),
            }
        )
    return out


def content_height(ws: List[Window], free_reset: bool = False) -> int:
    """Высота карточки под переданные окна лимита — повторяет то, как
    app/overlay.py раскладывает строки по высоте (шкала, время до сброса,
    кнопка "Бесплатный сброс"), чтобы окно всегда было ровно по содержимому.
    Вынесено сюда, а не в overlay.py, чтобы проверять тестами без tkinter."""
    if not ws:
        return LAYOUT_NO_DATA_H + LAYOUT_PAD * 2
    y = LAYOUT_PAD
    for win in ws:
        y += LAYOUT_BAR_H
        if win.get("reset"):
            y += LAYOUT_RESET_H
        if win.get("key") == "seven_day" and free_reset:
            y += LAYOUT_BTN_GAP + LAYOUT_BTN_H
        y += LAYOUT_ROW_GAP
    return y + LAYOUT_PAD


def fill_width(bar_w: float, used: float, min_px: float) -> float:
    """Ширина залитой части шкалы в пикселях по проценту использования.

    При used == 0 заливки нет вообще (0 px) — лимит полностью доступен,
    шкала должна выглядеть полностью пустой. При used > 0 ширина не может
    быть меньше min_px (обычно равен высоте шкалы — иначе скруглённые
    углы залитой части рисуются некорректно / кусочек пропадает совсем
    при очень маленьком, но не нулевом использовании). Без этого нижнего
    предела для used == 0 полоска всегда показывала бы видимый залитый
    кусочек даже при полностью свежем, неиспользованном лимите — создавая
    впечатление, будто часть лимита уже потрачена."""
    if used <= 0:
        return 0
    return max(min_px, round(bar_w * used / 100))


def label_position(bar_w: float, fill_w: float, label_px_w: float) -> tuple:
    """Где (якорь east, считая от левого края шкалы) и каким цветом рисовать
    подпись процента. По умолчанию — у правого края шкалы, светлым текстом
    (на тёмной дорожке). Когда заливка подбирается настолько близко, что
    перекрыла бы подпись на обычном месте, — подпись "уезжает" внутрь уже
    закрашенной части и становится тёмной: иначе она либо перекрывается
    заливкой, либо (если красить всегда тёмным) теряется на тёмной дорожке,
    пока заливка до неё не дошла."""
    right = bar_w - _LABEL_MARGIN
    left = right - label_px_w
    if fill_w >= left:
        right = max(fill_w - _LABEL_MARGIN, label_px_w)
        return right, True
    return right, False


def is_text_covered(used: float, text_center_pct: float) -> bool:
    """Решает, попадает ли центр подписи процента (text_center_pct, 0-100 —
    позиция вдоль шкалы) под уже закрашенную часть (used, 0-100). Если да —
    подпись нужно рисовать тёмным цветом (на ярком фоне заливки), иначе —
    светлым (на тёмной дорожке шкалы). Вынесено отдельно от отрисовки, чтобы
    не зависеть от tkinter в тестах."""
    return used >= text_center_pct


def tooltip_text(data: Optional[Dict[str, Any]], now: Optional[datetime] = None) -> str:
    """Текст для всплывающей подсказки в трее."""
    ws = windows_from_data(data, now)
    if not ws:
        return "Лимит Claude: нет данных"
    lines = []
    for w in ws[:2]:
        label = LABELS[w["key"]][1]
        line = f"{label}: осталось {w['left']}%"
        if w["reset"]:
            line += f" · {w['reset']}"
        lines.append(line)
    return "\n".join(lines)
