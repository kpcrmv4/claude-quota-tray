# Changelog

All notable changes to this fork are documented here.

**Upstream baseline:** [kpcrmv4/claude-quota-tray](https://github.com/kpcrmv4/claude-quota-tray) v0.2.0  
**Concept inspiration:** [Clawdmeter](https://github.com/HermannBjorgvin/Clawdmeter) (ESP32 hardware meter)

---

## [Unreleased] — fork (robonin9)

Changes compared to upstream v0.2.0. Tray UI, polling, history, and notifications are otherwise the same unless noted.

### Accuracy (api_client.py, history.py)

- **Quota parsing grounded in the real header format.** Verified against Anthropic docs and observed Claude Code/Max responses: `anthropic-ratelimit-unified-*-utilization` is a **fraction 0.0–1.0** (e.g. `0.0184` = ~2 %, `1` = 100 %), and `*-reset` is a **Unix epoch timestamp**. `_pct_from_utilization` now documents this, rounds half-up so tiny usage (`0.005` → 1 %) is not swallowed, and only falls back to "already a percentage" for values > 1. (Note: the previously suspected "`1` read as 100 %" is in fact *correct* for the real fractional format — `1` genuinely means full.)
- **Robust reset parsing.** `_seconds_until_reset` now tries numeric epoch first (the real format) with a clear 2020-01-01 epoch/relative split, then RFC 3339 / ISO 8601, then relative seconds — instead of a `now/2` heuristic.
- **Separate weekly Opus limit captured.** Unified windows are now discovered dynamically by scanning header names, so the Max-plan weekly **Opus** cap (`…-7d_oauth_opus-utilization`, or any future rename) is read and shown in the tooltip and tray menu instead of being silently dropped. New optional `opus_*` fields on `UsageSnapshot` (back-compatible).
- **No hallucinated burn-rate ETAs.** `history.burn_rate` now ignores samples before the most recent quota reset (a drop in %), reports 0 (not negative) when flat/recovering, requires a minimum growth rate before projecting an ETA, and caps projections — so "time to full" no longer appears when usage is flat or a window just rolled over.
- **`UsageSnapshot.http_status`** recorded for diagnostics; 4xx/5xx responses that still carry usable unified headers (e.g. a 429) remain `ok` and keep updating the badge.
- **Tests:** new `tests/` suite (`test_api_client.py`, `test_history_burn.py`) covering `_pct_from_utilization`, `_seconds_until_reset`, header→snapshot mapping, and burn-rate edge cases. Run with `python -m unittest discover -s tests`.

### New features (UX)

- **Near-reset notification.** When a limit you actually leaned on (≥ 40 %) is within `reset_notice_minutes` (default 10) of resetting, a toast tells you it's almost back. Fires at most once per limit per cycle and re-arms when the window rolls over. Toggle with `notify_before_reset`. Honours the alert snooze.
- **Adaptive poll interval.** New **Auto (adaptive)** option under *Settings → Check frequency* (`poll_interval_seconds = 0`): polls fast (30 s) when usage is high, climbing quickly, or a window is seconds from resetting; eases off (up to 5 min) when usage is low and flat. Saves request cost while staying responsive when it matters. The fixed 30 s / 1 m / 2 m / 5 m options are unchanged.
- **Weekly & monthly usage summary.** New tray items **Export weekly summary…** (7 days) and **Export monthly summary…** (30 days) write a Markdown report (peak 5-hour / weekly / Opus utilisation, busiest hour of day, and how many samples hit your alert threshold) and open it. The report states the actual covered range, so it's honest when history is shorter than the window. Choosing monthly transparently raises `history_retention_days` to at least 31 (only ever upward, with a toast) so future monthly reports are complete. History now also stores per-snapshot Opus % via an additive `opus_pct` column (old DBs migrate automatically; old rows stay valid). Internals: `history.period_summary(days, …)` / `export_period_summary(…)`, with `weekly_summary` / `export_weekly_summary` kept as 7-day wrappers.
- **Opus weekly bar + auth health in the status popup.** The left-click popup now shows a third progress bar for the weekly Opus limit (only when the account exposes it), plus a footer line with the active auth source and token expiry. The tray tooltip also shows a token-expiry warning when it's within 24 hours.

### Stability / bug fixes (main.py, history.py, desktop_widget.py)

- **CSV export no longer crashes.** `history.export_csv` used the `csv` module without importing it — any "Export CSV" click raised `NameError`. Added the import (covered by a regression test).
- **Poll loop is now crash-proof per iteration.** The fetch → record → burn-rate → notify path is wrapped so a network drop, DNS failure, lost token, unexpected API schema change, or SQLite hiccup logs to `error.log` and backs off (exponential, capped) instead of bubbling out and forcing a full poller restart.
- **SQLite concurrency hardened.** History opens in **WAL** mode with a `busy_timeout`, so the chart window's reads don't block the poller's writes (and vice-versa) and brief locks resolve instead of erroring.
- **Tray/Tk race hardened.** `desktop_widget.refresh()` (called from the poll thread) now snapshots the window reference under its lock before `.after()`, so a concurrent `hide()` on the UI thread can't trigger an `AttributeError`. Confirms the existing rule: the poll thread only ever marshals UI work via `after()`/badge updates, never touches the Win32 menu directly.

### Auth coverage (auth_discovery.py, token_reader.py, accounts.py, main.py)

- **Fallback past invalid tokens.** When the active token returns 401/403, the app now records it as bad and falls through to the next discovery source (env → Desktop → Credential Manager → credential files) instead of getting stuck retrying the dead one. `read_credentials` / `get_credentials` take an `exclude_tokens` set; the bad-token list is cleared on manual re-auth, account switch, and settings changes (so a fresh login at the same source is retried). Exclusion is by exact token value, so a re-login auto-heals.
- **Clearer auth errors.** Auth failures are detected via `http_status` (401/403) as well as the message text, and when every discovered token is rejected the error explicitly says so and tells the user to sign in again.
- **Richer `--probe` diagnostics.** `python src/token_reader.py --probe` now reports, per source: the resolved sub-source, a token fingerprint (so two sources sharing one token are obvious), the detected plan, and expiry status (`expires in 319d` / `EXPIRED`). Output is ASCII-safe for the Windows console.

### Added

- **History UI** — separate Session / Weekly chart panels, **24h / 7d / 30d (monthly)** range, CSV export, hover tooltips (`chart_widget.py`). Selecting the 30-day range bumps `history_retention_days` upward (never down) so the monthly chart fills over time instead of being pruned at the 7-day default.
- **Desktop widget (Windows)** — always-on-top on-screen quota bar (`desktop_widget.py`).
- **UX** — status popup → open history; last poll in tooltip; snooze alerts 1h; copy status; open error.log; notify on new release; tray metric (5h / weekly / max); separate alert thresholds per limit; poll backoff on errors; Tk light/dark via `ui_theme.py`.
- **macOS (beta)** — `app_platform` / `platform_darwin`, unsigned `.app` CI artifact, `scripts/setup_mac.sh`.
- **Signing docs** — `docs/SIGNING.md`, optional `signtool` in release workflow when `WINDOWS_CERT_PFX` secret is set.
- **`requirements-dev.txt`** — includes PyInstaller for builds.
- **Custom app icon** — `assets/app.ico` for Startup shortcut and `.exe` (`scripts/generate_app_icon.py`); no more default Python icon after Setup/build.

- **GitHub auto-update** — tray menu **Install / update**: check releases, set `owner/repo`, download latest source zip or `.exe` (`src/updater.py`, `src/update_runner.py`).
- **Maintenance menu** — run Setup / Update / Uninstall `.bat`, open install folder.
- **`src/app_paths.py`** — detect source install vs frozen `.exe`.
- **`src/auth_discovery.py`** — unified OAuth discovery with platform-aware provider order.
- **`src/desktop_auth.py`** — read and decrypt Claude Desktop `oauth:tokenCache` (Chromium v10; DPAPI on Windows, Keychain on macOS).
- **Multi-source auth** (first match wins on Windows):
  1. `CLAUDE_CODE_OAUTH_TOKEN` / `ANTHROPIC_AUTH_TOKEN`
  2. Claude Desktop (`%LOCALAPPDATA%\Packages\Claude_*\...\Claude\config.json`)
  3. Windows Credential Manager (`Claude Code-credentials`, etc.)
  4. Claude Code credential files (`~/.claude/.credentials.json`, `CLAUDE_CONFIG_DIR`, …)
- **macOS auth paths** (for discovery helpers; tray app remains Windows-focused): Keychain + Desktop decryption.
- **Diagnostics:** `python src/token_reader.py --probe` — test each provider independently.
- **Plan detection** from credentials (subscription / rate-limit tier) for tooltip and menu.
- **Single-instance guard** on Windows (mutex + message if already running).
- **Tray auto-restart** — if `pystray` exits without Quit, wait 3s and restart the icon loop.
- **Setup toast** when no OAuth token is found (one-time, en + th via `i18n.py`).
- **`pycryptodome`** in `requirements.txt` (Windows/macOS) for Desktop token decryption.
- **PyInstaller** hidden imports for `auth_discovery`, `desktop_auth`, and `Crypto` (`build.bat` / `build.sh`).

### Changed

- **`src/token_reader.py`** — helpers + delegates `read_credentials()` to `auth_discovery`; expanded file search paths.
- **`src/main.py`** — poll thread updates icon/tooltip only; menu rebuild runs on the UI thread (`update_menu=True`) to avoid Win32 tray crashes; `icon.run(setup=_start_poller)`.
- **`src/i18n.py`** — setup toast strings; account dialog text documents all discovery sources (en + th).
- **`src/settings.py`** — migration sets `active_account_id` to the first account when missing.
- **`README.md`** — auth flow, project layout, system requirements (Desktop or Code).
- **`Setup claude quota tray.bat`** — install message mentions `pycryptodome`.
- **`Uninstall claude quota tray.bat`** — stop running `pythonw`/`python` for this project before deleting `.venv`.

### Unchanged from upstream (same behaviour)

- API polling via minimal Haiku request + `anthropic-ratelimit-unified-*` headers.
- Tray badge, popup, history chart, burn rate, thresholds, schedule, multi-account UI.
- Windows toast notifications, winsound alerts, theme detection, SQLite history.

### Notes

- Files that show as modified in git but match upstream content are line-ending only (CRLF/LF), not functional changes.

---

## [0.2.0] — upstream (kpcrmv4)

Initial release: Windows system tray quota monitor for Claude Code OAuth credentials.

See [upstream releases](https://github.com/kpcrmv4/claude-quota-tray/releases).
