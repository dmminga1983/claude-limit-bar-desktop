import json

from app import config


def test_defaults_when_no_file(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    c = config.Config()
    assert c.get("tray_enabled") is True
    assert c.get("overlay_enabled") is True
    assert c.get("poll_seconds") == 60
    assert c.get("overlay_x") is None


def test_set_persists_and_reloads(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    c = config.Config()
    c.set("overlay_enabled", False)
    c.set("overlay_x", 123)
    saved = json.loads((tmp_path / "ClaudeLimitBar" / "config.json").read_text(encoding="utf-8"))
    assert saved["overlay_enabled"] is False and saved["overlay_x"] == 123
    c2 = config.Config()
    assert c2.get("overlay_enabled") is False and c2.get("overlay_x") == 123
    assert c2.get("tray_enabled") is True  # нетронутые ключи остались по умолчанию


def test_corrupted_file_falls_back_to_defaults(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    d = tmp_path / "ClaudeLimitBar"
    d.mkdir()
    (d / "config.json").write_text("{ not json", encoding="utf-8")
    c = config.Config()
    assert c.get("tray_enabled") is True


def test_unknown_key_in_file_is_kept_but_defaults_still_apply(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    d = tmp_path / "ClaudeLimitBar"
    d.mkdir()
    (d / "config.json").write_text(json.dumps({"overlay_enabled": False}), encoding="utf-8")
    c = config.Config()
    assert c.get("overlay_enabled") is False
    assert c.get("tray_enabled") is True
