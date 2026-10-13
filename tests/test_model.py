from datetime import datetime, timedelta, timezone

from app import model


def test_color_for_thresholds():
    assert model.color_for(0) == "#4cd17a"
    assert model.color_for(49.9) == "#4cd17a"
    assert model.color_for(50) == "#f5c542"
    assert model.color_for(79.9) == "#f5c542"
    assert model.color_for(80) == "#ff5c5c"
    assert model.color_for(100) == "#ff5c5c"


def test_until_reset_empty():
    assert model.until_reset(None) == ""
    assert model.until_reset("") == ""


def test_until_reset_past_is_empty():
    now = datetime(2026, 10, 7, 12, 0, tzinfo=timezone.utc)
    past = (now - timedelta(minutes=5)).isoformat().replace("+00:00", "Z")
    assert model.until_reset(past, now) == ""


def test_until_reset_minutes():
    now = datetime(2026, 10, 7, 12, 0, tzinfo=timezone.utc)
    soon = (now + timedelta(minutes=37)).isoformat().replace("+00:00", "Z")
    assert model.until_reset(soon, now) == "сброс через 37 мин"


def test_until_reset_hours():
    now = datetime(2026, 10, 7, 12, 0, tzinfo=timezone.utc)
    later = (now + timedelta(hours=2, minutes=14)).isoformat().replace("+00:00", "Z")
    assert model.until_reset(later, now) == "сброс через 2 ч 14 мин"


def test_until_reset_days():
    now = datetime(2026, 10, 7, 12, 0, tzinfo=timezone.utc)
    later = (now + timedelta(days=3, hours=5)).isoformat().replace("+00:00", "Z")
    assert model.until_reset(later, now) == "сброс через 3 д 5 ч"


def test_windows_from_data_empty():
    assert model.windows_from_data(None) == []
    assert model.windows_from_data({}) == []


def test_windows_from_data_basic():
    now = datetime(2026, 10, 7, 12, 0, tzinfo=timezone.utc)
    data = {
        "five_hour": {
            "utilization": 60,
            "resets_at": (now + timedelta(hours=1)).isoformat().replace("+00:00", "Z"),
        },
        "seven_day": {
            "utilization": 20,
            "resets_at": (now + timedelta(days=2)).isoformat().replace("+00:00", "Z"),
        },
        "seven_day_opus": {"utilization": None},  # пропускаем, нет данных
    }
    ws = model.windows_from_data(data, now)
    assert [w["key"] for w in ws] == ["five_hour", "seven_day"]
    assert ws[0]["used"] == 60
    assert ws[0]["left"] == 40
    assert ws[0]["reset"] == "сброс через 1 ч 0 мин"
    assert ws[1]["used"] == 20
    assert ws[1]["left"] == 80


def test_windows_from_data_clamps_utilization():
    data = {"five_hour": {"utilization": 150, "resets_at": None}}
    ws = model.windows_from_data(data)
    assert ws[0]["used"] == 100
    assert ws[0]["left"] == 0

    data2 = {"five_hour": {"utilization": -10, "resets_at": None}}
    ws2 = model.windows_from_data(data2)
    assert ws2[0]["used"] == 0
    assert ws2[0]["left"] == 100


def test_tooltip_text_no_data():
    assert model.tooltip_text(None) == "Лимит Claude: нет данных"
    assert model.tooltip_text({}) == "Лимит Claude: нет данных"


def test_tooltip_text_basic():
    now = datetime(2026, 10, 7, 12, 0, tzinfo=timezone.utc)
    data = {
        "five_hour": {
            "utilization": 60,
            "resets_at": (now + timedelta(minutes=30)).isoformat().replace("+00:00", "Z"),
        },
        "seven_day": {"utilization": 20, "resets_at": None},
    }
    text = model.tooltip_text(data, now)
    assert text == "5 часов: осталось 40% · сброс через 30 мин\nнеделя: осталось 80%"


def test_tooltip_text_limits_to_two_windows():
    data = {
        "five_hour": {"utilization": 10, "resets_at": None},
        "seven_day": {"utilization": 10, "resets_at": None},
        "seven_day_sonnet": {"utilization": 10, "resets_at": None},
        "seven_day_opus": {"utilization": 10, "resets_at": None},
    }
    text = model.tooltip_text(data)
    assert text.count("\n") == 1


def test_content_height_no_data():
    assert model.content_height([]) == model.LAYOUT_NO_DATA_H + model.LAYOUT_PAD * 2


def test_content_height_grows_with_reset_and_button():
    one_window = [{"key": "five_hour", "used": 10, "left": 90, "reset": ""}]
    one_with_reset = [{"key": "five_hour", "used": 10, "left": 90, "reset": "сброс через 1 ч"}]
    bare = model.content_height(one_window)
    with_reset = model.content_height(one_with_reset)
    assert with_reset == bare + model.LAYOUT_RESET_H

    two_windows = one_window + [{"key": "seven_day", "used": 10, "left": 90, "reset": ""}]
    assert model.content_height(two_windows) == bare + model.LAYOUT_BAR_H + model.LAYOUT_ROW_GAP

    seven_day = [{"key": "seven_day", "used": 10, "left": 90, "reset": ""}]
    without_button = model.content_height(seven_day, free_reset=False)
    with_button = model.content_height(seven_day, free_reset=True)
    assert with_button == without_button + model.LAYOUT_BTN_GAP + model.LAYOUT_BTN_H

    # Кнопка "Бесплатный сброс" относится только к недельному лимиту.
    five_hour = [{"key": "five_hour", "used": 10, "left": 90, "reset": ""}]
    assert model.content_height(five_hour, free_reset=True) == model.content_height(five_hour, free_reset=False)


def test_fill_width_zero_used_means_no_fill_at_all():
    # Лимит полностью доступен (0% использовано) — заливки быть не должно,
    # даже учитывая минимальную ширину под скруглённые углы.
    assert model.fill_width(bar_w=65, used=0, min_px=12) == 0


def test_fill_width_tiny_nonzero_usage_still_respects_min_px():
    # Чуть-чуть использовано (например 2%) — заливка должна быть видна
    # хотя бы минимальной шириной, а не пропадать из-за округления вниз.
    assert model.fill_width(bar_w=65, used=2, min_px=12) == 12


def test_fill_width_scales_proportionally_once_above_min():
    assert model.fill_width(bar_w=100, used=60, min_px=12) == 60


def test_label_position_default_is_light_at_right_edge():
    # Заливка далеко от правого края шкалы — подпись на обычном месте, светлая.
    right, dark = model.label_position(bar_w=100, fill_w=20, label_px_w=18)
    assert dark is False
    assert right == 100 - 3  # bar_w - margin


def test_label_position_switches_to_dark_when_fill_approaches():
    # Заливка дошла до места, где обычно стоит подпись — подпись "уезжает"
    # внутрь заливки и становится тёмной.
    bar_w, label_px_w = 100, 18
    fill_w = bar_w - 3 - label_px_w + 1  # на 1px глубже, чем обычная левая граница подписи
    right, dark = model.label_position(bar_w=bar_w, fill_w=fill_w, label_px_w=label_px_w)
    assert dark is True
    assert right == fill_w - 3


def test_label_position_never_pushes_label_off_the_left_edge():
    # Даже когда заливка совсем маленькая, подпись не должна вылезать за
    # левый край шкалы (right всегда >= label_px_w).
    right, dark = model.label_position(bar_w=20, fill_w=0, label_px_w=18)
    assert right >= 18
