# Repository Guidelines

## Project Structure & Module Organization

This repository is an AstrBot plugin for QQ group interaction. The runtime code is currently concentrated in `main.py`, which registers the `xxt_fun` plugin and implements command handlers such as `/选人`. Plugin metadata lives in `metadata.yaml`; keep its `name`, `display_name`, `desc`, `version`, `author`, and `repo` fields aligned with code changes. `README.md` documents user-facing behavior and support links. There is no dedicated `tests/` or assets directory yet; add them only when needed, using clear top-level paths such as `tests/` and `assets/`.

## Build, Test, and Development Commands

- `python -m py_compile main.py`: checks Python syntax without starting AstrBot.
- `git status --short`: confirms which files are modified before committing.
- Run locally by placing this plugin directory under AstrBot's plugin directory, starting AstrBot, and testing commands in a QQ group through the configured OneBot adapter.

There is no build step for this repository. If new dependencies are introduced, document installation and runtime requirements in `README.md`.

## Coding Style & Naming Conventions

Use Python 3 style with 4-space indentation. Keep command handlers asynchronous and compatible with AstrBot's event APIs: handlers should accept `AstrMessageEvent`, validate input early, and `yield` AstrBot result objects. Use descriptive snake_case names for functions, variables, and helpers, for example `pick_count` and `pick_members`. Keep user-facing Chinese messages concise and consistent with existing punctuation. Avoid broad refactors when changing a command; prefer small, focused edits around the relevant handler.

## Testing Guidelines

No automated test suite exists yet. For every change, at minimum run `python -m py_compile main.py`. For behavior changes, manually test inside a QQ group and cover success plus validation cases, such as `/选人 1`, missing count, zero or negative count, and count greater than available members. If tests are added, prefer `pytest` under `tests/`, with files named `test_*.py`.

## Commit & Pull Request Guidelines

Git history is minimal (`init`, `Initial commit`), so use short imperative commit messages such as `Add member selection validation`. Pull requests should include a brief summary, manual test results, affected commands, and screenshots or chat logs when output behavior changes. Link related issues when available.

## Security & Configuration Tips

Do not commit bot tokens, adapter credentials, session files, or local AstrBot runtime data. Keep platform-specific assumptions explicit; this plugin currently depends on QQ group member data through OneBot-compatible AstrBot APIs.
