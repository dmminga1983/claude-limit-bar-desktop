"""Управление двумя способами показа (трей и плавающее окошко).

Правило: оба способа включаются и отключаются независимо, но хотя бы один
всегда остаётся включённым — иначе программа продолжила бы работать в фоне
без единого видимого элемента управления, и вернуть интерфейс можно было бы
только правкой config.json. Поэтому выключение последнего включённого
способа автоматически включает второй.

Модуль не импортирует GUI-библиотеки: tray и overlay передаются снаружи
(и подменяются заглушками в тестах).
"""
from typing import Any, Dict, Optional


class Controller:
    def __init__(self, cfg, tray, overlay, on_quit):
        self.cfg = cfg
        self.tray = tray
        self.overlay = overlay
        self.on_quit = on_quit
        self.last_data: Optional[Dict[str, Any]] = None

    # ---- начальное состояние ---------------------------------------------
    def apply_initial(self) -> None:
        tray_on = bool(self.cfg.get("tray_enabled"))
        overlay_on = bool(self.cfg.get("overlay_enabled"))
        if not tray_on and not overlay_on:
            # Конфиг с обоими выключенными — не оставляем пользователя без интерфейса.
            tray_on = True
            self.cfg.set("tray_enabled", True)
        if tray_on:
            self.tray.start()
        self.overlay.set_visible(overlay_on)

    # ---- переключатели ----------------------------------------------------
    def set_overlay(self, on: bool) -> None:
        if not on and not self.cfg.get("tray_enabled"):
            self._apply_tray(True)
        self._apply_overlay(on)

    def set_tray(self, on: bool) -> None:
        if not on and not self.cfg.get("overlay_enabled"):
            self._apply_overlay(True)
        self._apply_tray(on)

    def toggle_overlay(self) -> None:
        self.set_overlay(not self.cfg.get("overlay_enabled"))

    def toggle_tray(self) -> None:
        self.set_tray(not self.cfg.get("tray_enabled"))

    # ---- режим видимости окошка -------------------------------------------
    def get_overlay_mode(self) -> str:
        return str(self.cfg.get("overlay_mode") or "always")

    def set_overlay_mode(self, mode: str) -> None:
        self.cfg.set("overlay_mode", mode)
        self.overlay.set_mode(mode)

    def _apply_overlay(self, on: bool) -> None:
        self.cfg.set("overlay_enabled", bool(on))
        self.overlay.set_visible(bool(on))

    def _apply_tray(self, on: bool) -> None:
        self.cfg.set("tray_enabled", bool(on))
        if on:
            self.tray.start()
            self.tray.update(self.last_data)
        else:
            self.tray.stop()

    # ---- данные -----------------------------------------------------------
    def push(self, data: Optional[Dict[str, Any]]) -> None:
        self.last_data = data
        if self.cfg.get("tray_enabled"):
            self.tray.update(data)
        self.overlay.update(data)

    def push_free_reset(self, available: bool) -> None:
        self.overlay.set_free_reset(bool(available))

    def quit(self) -> None:
        self.on_quit()
