"""Авто-старт/стоп Claude Limit Bar вместе с десктоп-приложением Claude.

Лёгкий наблюдатель без GUI: поднимается при входе в Windows (ярлык в папке
автозагрузки) и раз в несколько секунд проверяет, запущен ли claude.exe —
если да и оверлей ещё не запущен, запускает app.main; если claude.exe пропал
(и не появился обратно в течение GRACE_POLLS проверок — переживаем короткие
перезапуски/окно crash-репортера), останавливает оверлей. Сам наблюдатель
почти ничего не ест — просто tasklist раз в несколько секунд.
"""
import subprocess
import sys
import time
from pathlib import Path

POLL_SECONDS = 4
GRACE_POLLS = 5  # ~20с отсутствия claude.exe, прежде чем гасить оверлей
PROJECT_ROOT = Path(__file__).resolve().parent.parent
PYTHONW = PROJECT_ROOT / ".venv" / "Scripts" / "pythonw.exe"

CREATE_NO_WINDOW = 0x08000000


def claude_running() -> bool:
    try:
        out = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq claude.exe", "/NH"],
            capture_output=True, text=True, timeout=5, creationflags=CREATE_NO_WINDOW,
        )
        return "claude.exe" in out.stdout.lower()
    except Exception:
        return False


def sweep_kill_stray_app() -> None:
    """Подчищает осиротевшие процессы app.main — например, если
    наблюдатель перезапустился и потерял ссылку на старый Popen, или
    app.main запустил побочный процесс (у pywebview такое бывает).

    Фильтр нарочно требует совпадения и по "app.main", И по пути нашего
    проекта в командной строке — просто "app.main" было бы слишком широким
    совпадением: на машине теоретически может найтись другой, никак с нами
    не связанный процесс с таким же именем модуля, и его мы убивать не
    должны."""
    try:
        root_escaped = str(PROJECT_ROOT).replace("'", "''")  # экранируем на случай кавычки в пути
        ps_cmd = (
            "Get-CimInstance Win32_Process | "
            f"Where-Object {{ $_.CommandLine -like '*app.main*' -and $_.CommandLine -like '*{root_escaped}*' }} | "
            "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
        )
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_cmd],
            capture_output=True, timeout=10, creationflags=CREATE_NO_WINDOW,
        )
    except Exception:
        pass


def launch_app():
    return subprocess.Popen(
        [str(PYTHONW), "-m", "app.main"],
        cwd=str(PROJECT_ROOT),
        creationflags=CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS,
    )


def main() -> None:
    sweep_kill_stray_app()  # на случай осиротевшего процесса с прошлого раза
    proc = None
    absent_polls = 0
    while True:
        try:
            running = claude_running()
            if running:
                absent_polls = 0
                if proc is None or proc.poll() is not None:
                    proc = launch_app()
            else:
                absent_polls += 1
                if proc is not None and absent_polls >= GRACE_POLLS:
                    try:
                        proc.terminate()
                    except Exception:
                        pass
                    proc = None
                    sweep_kill_stray_app()
        except Exception:
            pass
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
