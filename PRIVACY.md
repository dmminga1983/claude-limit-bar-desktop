# Privacy Policy

**Project:** Claude Limit Bar — Windows desktop app
**Date:** 2026-10-09

This is an unofficial desktop application, not an official Anthropic product and not affiliated with Anthropic.

## What data it processes

The app never touches or decrypts your browser's cookies. On first launch it opens its own embedded claude.ai sign-in window; you sign in there once, exactly like in a normal browser, and the app saves that session locally on your machine (nowhere else). From then on it calls the same internal endpoint claude.ai's own web UI uses, `/api/organizations/.../usage`, on behalf of that saved session, purely to read your usage status — this doesn't spend messages or count against your limit.

## What the app does NOT do

- Collect, store, or transmit passwords, credentials, or personal messages.
- Send any data to the author's servers or any third party — there is no networking code beyond reading data from claude.ai itself.
- Use analytics, trackers, or ad networks.
- Run on, or request access to, any site other than claude.ai.

## Data storage

The saved claude.ai session and your settings (`%APPDATA%\ClaudeLimitBar\config.json`) stay on your computer; neither is sent anywhere by the app.

## Source code

The app is a handful of Python files under `app/` — you're welcome to read it yourself: https://github.com/dmminga1983/claude-limit-bar-desktop

## Contact

For anything related to this app, open an issue on the GitHub repository.
