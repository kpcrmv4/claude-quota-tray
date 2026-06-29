# Code signing

## Windows (.exe)

Unsigned PyInstaller builds often trigger Windows Defender / SmartScreen. To publish a signed executable:

1. Purchase an **OV or EV** code-signing certificate from a public CA (Sectigo, DigiCert, etc.).
2. Export a `.pfx` file and keep the password secret.
3. Sign locally:

```bat
signtool sign /f your-cert.pfx /p YOUR_PASSWORD ^
  /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 ^
  dist\ClaudeQuotaTray.exe
```

### GitHub Actions (optional)

Add repository secrets:

- `WINDOWS_CERT_PFX` — base64-encoded `.pfx`
- `WINDOWS_CERT_PASSWORD` — PFX password

The release workflow signs the `.exe` when these secrets exist. Without them, releases stay **unsigned**.

Self-signed certificates do **not** help end users bypass SmartScreen.

## macOS (.app)

This project does **not** use Apple Developer ID or notarization. macOS builds are **unsigned**.

- **Recommended:** run from source (`python3` + virtualenv).
- If using a release `.app`, you may need **Right-click → Open** the first time (Gatekeeper).

Notarization can be added later if you obtain an Apple Developer account.
