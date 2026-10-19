# Claude Limit Bar — Desktop App (Windows)

**See your Claude usage limit before you hit it — never get cut off mid-task again.** The same idea as a browser extension, but as a standalone **Windows 10/11** program that keeps working even when the browser is closed. A glass (glassmorphism / Liquid Glass) overlay card, a color-coded tray icon, and a choice of where to show it.

Reads the exact same usage numbers your own account already sees, renders them locally, and talks to nothing but claude.ai — no account, no server, no tracking, no telemetry. Free and open-source (MIT).

[Русская версия →](README.ru.md)

Just want it in the browser instead? See [claude-limit-bar-extension](https://github.com/dmminga1983/claude-limit-bar-extension) (Chrome and Chromium-based browsers).

> **Pasted this link into regular Claude chat (claude.ai) and said "install"?** That won't work from there — the regular chat can only read files you attach, it has no access to your computer's terminal. You need **Claude Code** instead (it's free to try and comes with a Claude subscription). Quick switch:
>
> 1. Open PowerShell and install it (skip if you already have it):
>    ```powershell
>    irm https://claude.ai/install.ps1 | iex
>    ```
>    (or, with WinGet: `winget install Anthropic.ClaudeCode`)
> 2. Open a terminal and run `claude` to start a session.
> 3. Paste the block from **"Install via Claude Code"** below into that session — it does the rest itself.
>
> Full install docs if anything above doesn't work: https://code.claude.com/docs/en/quickstart

There are two display modes, **each can be turned on or off independently**:

1. **System tray icon** — an icon with a bar for the remaining limit (green → yellow → red, by whichever is worse of the two windows — 5-hour and weekly), with a tooltip on hover showing percentages and time until reset.
2. **Floating overlay window** — a small glass card (real background blur via Windows Acrylic, with a clean fallback to a drawn "glass" look if the system doesn't support it). Shows both bars with color and percentages, large and readable. Left-click to drag (position is remembered), right-click for the menu. Release the window near a screen edge or corner (within ~24px) and it snaps to it.

The overlay window has two visibility modes (via the right-click menu's "Show" submenu, or from the tray icon → "Show window"):

- **Always on top** — a normal always-on-top window, visible no matter what else is open.
- **Only while using Claude** — the window appears only while the Claude desktop app window or a claude.ai browser tab is in the foreground, and hides the rest of the time.

Both toggles are reachable from either place:

- right-click the tray icon → "Floating overlay window" (checkbox), "Show window" (submenu with the two modes above);
- right-click the overlay window → "Hide window", "Tray icon" (checkbox), "Show" (same submenu), "Quit".

At least one display method (tray/overlay) always stays enabled: turning off the last enabled one turns the other back on automatically — otherwise there'd be no way to control the app anymore.

## How it gets its data

The app never touches or decrypts browser cookies. On first launch it opens its own claude.ai sign-in window, saves the session once, and then works autonomously: it calls the same internal endpoint, `/api/organizations/.../usage`, that the extension uses, on behalf of that session. Nothing leaves your machine except calls to claude.ai itself. Polling the limit is a read of your own status, same as the site's UI — it doesn't spend messages or count against your limit.

> Signing in via "Continue with Google" inside the embedded window may be blocked by Google itself (it refuses to work inside embedded browsers). If that happens, sign in with your email address and password/code instead.

## Install via Claude Code (easiest)

If [Claude Code](https://claude.com/claude-code) is already on the computer, you don't need to do anything by hand: copy the whole block below and send it to Claude Code (not the regular claude.ai chat — that has no access to your terminal). Claude Code has real terminal access on this machine, so it will check for Python, clone the repository, install dependencies, run the tests, and start the app itself — it will only ask you something if it hits a real problem (e.g. Python isn't installed).

```
Install the Claude Limit Bar desktop app for Windows for me — it's a
remaining-usage indicator for Claude.ai (tray icon + floating overlay
window).

Repository: https://github.com/dmminga1983/claude-limit-bar-desktop

Do this in order:
1. Check that git and python are available (version 3.10+; running
   `python` must NOT open the Microsoft Store — if it does, that's the
   store's stub, not real Python; warn me and stop, don't install
   anything yourself).
2. Clone the repository into
   C:\Users\<my_username>\Documents\ClaudeLimitBar — if a folder with
   that name already exists and isn't a git repository, ask me whether
   it's OK to replace it, don't delete anything silently.
3. Inside that folder, create a virtual environment (.venv) and install
   the dependencies from requirements.txt.
4. Run the tests (pytest) — if anything fails, show me exactly what,
   and don't continue silently.
5. Start the app (python -m app.main) in the background and add it to
   Windows startup (a shortcut in Startup), so it comes up on its own
   when I log in — as described in this repo's README.md (there's an
   install.bat that does all of this; feel free to just run it instead
   of doing every step by hand).
6. At the end, tell me briefly what worked and what I still need to do
   by hand (e.g. signing into claude.ai once in the pop-up login window).
```

After that, the first launch will open a claude.ai sign-in window — you sign in once by hand, just like in a normal browser (that's the app itself asking, Claude Code has nothing to do with that part — it just starts the app).

> This isn't about the regular claude.ai chat — Claude can't install anything on your computer from there, it can only read files you attach. You specifically need Claude Code (installed separately, it has a terminal).

## Manual install on Windows 10/11

You need **real Python 3.12** from [python.org](https://www.python.org/downloads/) (check "Add python.exe to PATH" during install) and the Microsoft Edge WebView2 runtime (usually already present on Windows 10/11).

> Heads up: if running `python` in a terminal opens the Microsoft Store, or silently does nothing, that's not Python — it's the Store's app-execution-alias stub. Install Python from python.org (or disable the stub: Settings → Apps → App execution aliases → turn off "python.exe").

Download the repository (**Code → Download ZIP** on the GitHub project page, or `git clone`) and just **double-click `install.bat`**. It will create a virtual environment, install dependencies, run the tests, add the app to startup, and launch it — details and any errors land in `install_log.txt` next to it.

The same thing done manually:

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m app.main
```

On first launch a claude.ai sign-in window opens — sign in as usual. After signing in, the window hides and the tray icon and/or overlay window appear.

### Normal startup vs. debugging

After installation the app is already added to Windows startup and launches on its own, with no visible window at all. To start it by hand, there are two options:

- **`start_silent.bat`** — the normal way. Runs the app via `pythonw.exe`: no console window, nothing in your way. There's nothing to close or minimize — the app just runs in the background, with only the tray icon and/or the overlay window visible.
- **`debug_console.bat`** — for debugging only. Runs via the regular `python.exe` in a visible console window, so you can see errors and tracebacks. **Closing that window stops the whole app** — that's expected; this mode isn't for everyday use.

If you see a console window and everything disappears when you close it, that means it was started via `debug_console.bat`. Use `start_silent.bat` instead.

### Building a single .exe (optional)

```powershell
pip install pyinstaller
pyinstaller --noconsole --onefile --name ClaudeLimitBar -p . app\main.py
```

The file will show up at `dist\ClaudeLimitBar.exe`.

## Settings

Stored as JSON at `%APPDATA%\ClaudeLimitBar\config.json`.

| Key               | What it means                                                              |
| ----------------- | --------------------------------------------------------------------------- |
| `tray_enabled`     | whether to show the tray icon                                             |
| `overlay_enabled`  | whether to show the floating overlay window                               |
| `overlay_mode`     | `always` (always on top) or `claude_only` (only while Claude is active)   |
| `overlay_x/y`      | last window position (remembered automatically, with edge snapping)       |
| `poll_seconds`     | how often to poll the limit (minimum 15, default 60)                      |

## Tests

The bar logic, toggles, client (against a fake webview window), config, window edge-snapping, and visibility mode don't depend on any GUI library:

```bash
pip install pytest
pytest
```

## Limitations

- The webview + tray + Tk integration has only been verified piecemeal (logic and icon rendering — by tests; the actual windows live — on the author's own Windows machine), so a first run on a new machine may hit small rough edges: send over `install_log.txt`/`trace.log` or the error text if so.
- "Only while using Claude" mode detects the active window by its title (looking for the word "Claude") — this applies to both the desktop app and a browser tab, but in rare cases (a non-standard tab title) it may not catch on right away.
- Windows 10/11 only; macOS and Linux aren't supported.

## Privacy & license

Full privacy policy: [PRIVACY.md](./PRIVACY.md). Free and open-source for any purpose — [MIT License](./LICENSE).

## Like it?

A ⭐ on the repo tells me people actually want this — it's the only metric that keeps this project alive.
