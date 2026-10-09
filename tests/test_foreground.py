from app.foreground import claude_is_foreground, foreground_window_title


def test_claude_desktop_app_title():
    assert claude_is_foreground("Claude") is True


def test_browser_tab_title_with_claude():
    assert claude_is_foreground("Моя задача - Claude") is True


def test_case_insensitive():
    assert claude_is_foreground("CLAUDE") is True


def test_unrelated_window_title():
    assert claude_is_foreground("YouTube - Google Chrome") is False


def test_empty_title():
    assert claude_is_foreground("") is False


def test_foreground_window_title_does_not_crash():
    # На не-Windows (CI) обращение к WinAPI само по себе недоступно — функция
    # должна тихо вернуть "", а не упасть с исключением.
    assert isinstance(foreground_window_title(), str)
