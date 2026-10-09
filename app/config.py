"""Настройки приложения: включены ли трей/оверлей, позиция оверлея и т.п.
Хранится в JSON в стандартной пользовательской папке конфигов.
"""
import json
import os
import sys
from pathlib import Path
from typing import Any

DEFAULTS = {
    "tray_enabled": True,
    "overlay_enabled": True,
    "overlay_x": None,
    "overlay_y": None,
    "overlay_mode": "always",  # "always" — поверх всех окон; "claude_only" — только когда активно окно/вкладка Claude
    "poll_seconds": 60,
}


def config_dir() -> Path:
    appdata = os.getenv("APPDATA")  # Windows
    if appdata:
        base = Path(appdata)
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path.home() / ".config"  # на случай запуска не на Windows/macOS
    d = base / "ClaudeLimitBar"
    d.mkdir(parents=True, exist_ok=True)
    return d


def config_path() -> Path:
    return config_dir() / "config.json"


class Config:
    def __init__(self):
        self.data = dict(DEFAULTS)
        self.load()

    def load(self) -> None:
        p = config_path()
        if p.exists():
            try:
                self.data.update(json.loads(p.read_text(encoding="utf-8")))
            except (json.JSONDecodeError, OSError):
                pass

    def save(self) -> None:
        try:
            config_path().write_text(
                json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except OSError:
            pass

    def get(self, key: str) -> Any:
        return self.data.get(key, DEFAULTS.get(key))

    def set(self, key: str, value: Any) -> None:
        self.data[key] = value
        self.save()
