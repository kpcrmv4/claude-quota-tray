# Security Policy

## Supported versions

Only the latest release line receives fixes. This is a small single-developer
fork, so please always run the most recent version before reporting an issue.

| Version | Supported          |
| ------- | ------------------ |
| 0.3.x   | :white_check_mark: |
| < 0.3   | :x:                |

## How the app handles your credentials

Claude Quota Tray is designed to touch your OAuth credentials as little as
possible:

- **Read-only.** The app only *reads* the Claude OAuth token that already
  exists on your machine (Claude Desktop, Windows Credential Manager,
  environment variables, or Claude Code credential files). It never writes,
  rotates, or modifies your credentials.
- **No token storage.** The token is held in memory only for the duration of a
  request. It is **never** written to `settings.json`, `history.db`, or the
  log. Settings store only a *path* or the `auto` discovery mode — never the
  token value itself.
- **Single destination.** The token is sent only to `https://api.anthropic.com`
  over HTTPS, in a minimal request whose response body is ignored — the app
  reads usage from the `anthropic-ratelimit-unified-*` response headers only.
- **Local-only data.** History (`history.db`) stores just timestamps and
  utilisation percentages. No prompts, completions, account identifiers, or
  token material are recorded.
- **Logs are safe to share.** `error.log` records diagnostics and token-refresh
  events but never the token itself (probes print only a short fingerprint such
  as `sk-ant...GAAA`).

All of this is auditable — the project is open source (MIT). You can verify the
auth flow in `src/auth_discovery.py`, `src/token_reader.py`, and the request in
`src/api_client.py`, or run `python src/token_reader.py --probe` to see exactly
which source is used (the probe masks the token).

## Reporting a vulnerability

If you believe you have found a security issue:

1. **Preferred:** open a private [GitHub Security Advisory](https://github.com/robonin9/claude-quota-tray/security/advisories/new)
   on this repository.
2. Alternatively, open a regular [issue](https://github.com/robonin9/claude-quota-tray/issues)
   — but please do **not** include tokens, credentials, or other secrets in a
   public issue.

Please include the version, your OS, reproduction steps, and the impact you
observed. As a hobby project, responses are best-effort: expect an initial reply
within a couple of weeks. Accepted issues will be fixed in the next release and
credited (if you wish); out-of-scope reports will get a short explanation.

## Scope notes

- Released `.exe` / `.app` builds are **unsigned** unless a maintainer signs
  them — see [docs/SIGNING.md](docs/SIGNING.md). Antivirus/SmartScreen warnings
  on an unsigned PyInstaller build are expected and are not themselves a
  vulnerability. When in doubt, run from source.
- The app's security depends on the integrity of the machine it runs on. If the
  local credential stores it reads from are already compromised, this tool
  cannot protect them.
