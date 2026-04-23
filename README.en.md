# Outlook Email Plus

[中文 README](./README.md) · [Release Playbook](./RELEASE.md)

OutlookMail Plus is a mailbox manager built for individuals and teams that work heavily with registration flows.

Unlike general-purpose email clients, it focuses on **registration and verification** workflows and is deeply optimized around getting those flows done quickly.

### Why OutlookMail Plus

- **Built for registration workflows**: it removes unnecessary steps as much as possible. You can copy mailbox addresses with one click; after sending a verification email on a signup page, you can return to the manager, click "Verification Code", fetch the latest email, and quickly extract the code or verification link with regex.
- **Lighter and more focused**: non-core features such as sending mail are intentionally left out, so the interface stays cleaner and every design choice is centered on completing registration tasks.
- **Broader import compatibility**: it supports mainstream mailbox providers such as Gmail, QQ, and 163, as well as custom IMAP servers. Self-hosted mailboxes also work. Built-in CF Worker temp mailboxes support multi-domain configuration and Admin Key encryption, significantly reducing privacy exposure in registration workflows.
- **Automation-friendly**: it exposes APIs for batch registration workflows; the mail pool supports project-scoped claiming via `project_key`. For long-lived mailboxes, when `project_key + caller_id + task_id` are explicitly provided during claim, a mailbox with a recorded success in the same project will not be re-claimed, and `claim-complete(result=success)` returns it directly to `available`, allowing immediate reuse by other projects. Temp mail / `cloudflare_temp_mail` keep the legacy behavior. Mailbox claiming, verification-code retrieval, and release are all covered.
- **Third-party notifications**: third-party notification channels are supported. Telegram is already integrated, and important mailboxes can push alerts automatically.

In short, OutlookMail Plus is a mailbox manager designed specifically for registration workflows.

## Demo Site

Demo site: https://demo.outlookmailplus.tech/  
Login password: `12345678`

The site includes 10 mailbox accounts for demonstration. Data is periodically reset. Please do not delete the demo accounts or use them for personal purposes.

The demo covers most major features in this project, except Telegram push (which requires additional configuration).

## UI Preview

The repository already includes some screenshots, and more can be added later.

![Dashboard](img/仪表盘.png)
![Mailbox View](img/邮箱界面.png)
![Verification Code Extraction](img/提取验证码.png)
![Settings](img/设置界面.png)

## Version Highlights

Current stable version: `v2.2.2`

### Recent Version Overview

| Version | Date | Key New Features |
|---------|------|-----------------|
| **v2.2.0** | 2026-04 | 🔌 **Temp Mail Provider Plugin System**: dynamic install/unload/configure/hot-reload for third-party providers; built-in Cloudflare / Custom / GPTMail / Moemail; provider settings decoupled from domain selection; browser extension adds local personal-info generator and full Jest coverage |
| **v2.1.0** | 2026-04 | 📊 **Overview Dashboard**: a 5-tab unified board (Summary / Verification / External API / Mailbox Pool / Activity), plus `verification_extract_logs` for shared observability, browser-extension API-key copy fix, and overview real-time/i18n polish |
| **v2.0.0** | 2026-04 | 🌐 **Browser Extension** (Chrome/Edge MV3): one-click claim → auto-extract verification code/link → complete/release, no tab-switching needed; backend adds `chrome-extension://` CORS support |
| **v1.19.0** | 2026-04 | 🔧 Structured refresh-failure hints (error code + actionable steps + trace guide); fixed Selected account refresh early-exit (Issue #45) |
| **v1.18.0** | 2026-04 | 🔄 Mail pool **project-scoped success reuse**: with explicit `project_key + caller_id + task_id`, `success` returns mailbox to `available` for immediate cross-project reuse (DB v22) |
| **v1.17.0** | 2026-04 | 🪝 **Webhook notification channel**: single global URL, co-exists with Email/Telegram; one-click random X-API-Key generation |
| **v1.16.0** | 2026-04 | 🔑 OAuth Token tool upgrade: new "Get Authorization Link" mode for stable cross-environment auth |
| **v1.15.0** | 2026-04 | 🤖 **AI verification-code enhancement**: system-level AI fallback (only when both confidence scores are low), fixed JSON contract; **email alias** (`+tag`) auto-normalization |
| **v1.13.0** | 2026-04 | ⚡ **One-click hot-update**: Watchtower (recommended) and Docker API dual modes, auto-detect new version with in-app banner |
| **v1.11.0** | 2026-04 | 🏊 **Mail pool project isolation** (`project_key`); CF Worker multi-domain + Admin Key encryption; frontend account list pagination; unified poll engine |
| **v1.9.0** | 2026-03 | 🌐 **Bilingual UI** (Chinese/English); unified notification dispatch (Email + Telegram); demo-site password lock |

---

### v2.1.0 — Overview Dashboard & Observability

- Added a 5-tab overview dashboard to replace the old dashboard page
- Added `verification_extract_logs` to unify observability across regular-mailbox, temp-mail, and external-API verification extraction paths
- Fixed the real browser-extension “API invalid” causes: copying masked API keys and misunderstanding `external pool` / `pool_access` prerequisites
- Completed overview real-time refresh and i18n polish, so header / tabs / hover notes / timeline now stay consistent with the main cards

### v2.0.0 — Browser Extension (New)

The `browser-extension/` directory contains a Chrome/Edge Manifest V3 extension. See the [Browser Extension](#browser-extension) section below.

### v1.15.0–v1.16.0 — OAuth Token Tool

- Added a dedicated popup-style token tool for **compatibility-mode account import**
- The supported contract is now fixed to personal Microsoft accounts: Public Client, `tenant=consumers`, and no `client_secret`
- The Azure app registration should use **Accounts in any identity provider or organizational directory and personal Microsoft accounts**; org-only apps fail with `unauthorized_client`, while **Personal Microsoft accounts only** conflicts with the current `/common` validation/runtime model and can fail with `AADSTS9002331`
- If Azure blocks the audience change with `Property api.requestedAccessTokenVersion is invalid`, update `api.requestedAccessTokenVersion` to `2` in the **Manifest** first
- If you hit `AADSTS70000` (unauthorized/expired scope), first verify that the scope used during consent matches the scope used during validation, then run a fresh **forced-consent** authorization
- Recommended minimum Graph delegated permissions: **offline_access + Mail.Read + User.Read**; add **Office 365 Exchange Online → IMAP.AccessAsUser.All** only when IMAP is required
- Supports Graph / IMAP scope presets, error guidance, and JWT audience/scope diagnostics; the frontend now recommends the **Graph mail preset** by default (backend env fallback remains IMAP-compatible)
- Built-in Azure quick-start guide card (5 steps) and tutorial link: <https://real-caption-6d1.notion.site/OutlooKMailplus-token-344463aed7e680099380dc324ecdf1c9?source=copy_link>
- Supports writing refresh tokens into existing Outlook accounts or creating new accounts after validation, while rejecting incompatible configurations

### v1.13.0 — One-Click Update

- Two update methods: Watchtower (recommended) and Docker API self-update (advanced)
- Automatic GitHub release detection with in-app update banner
- Full deployment info detection: image tag, local build, Watchtower connectivity, etc.
- Watchtower "already latest" smart detection (based on Watchtower synchronous behavior)
- Docker API digest pre-check — skips update when already on latest version

### v1.11.0 — Mail Pool & Frontend Enhancements

- **Mail pool project isolation**: `project_key` prevents duplicate claiming in the same project (DB v17)
- **CF Worker multi-domain support**: configure multiple CF Worker domains in Settings; "Sync Domains" button refreshes the list in one click
- **Admin Key encrypted at rest**: `cf_worker_admin_key` stored with `enc:` prefix (DB v18)
- **Frontend account list pagination**: 50 accounts per page for smoother rendering
- **Unified poll engine**: merged dual polling systems (standard + compact) into single `poll-engine`, fixing race conditions and state accumulation

## Core Capabilities

- Multi-mailbox management
  Supports Outlook OAuth, regular IMAP mailboxes, and CF Worker temp mailboxes (multi-domain configuration, Admin Key encrypted at rest)
- Bulk import and organization
  Supports bulk import, tags, search, groups, and export
- Mail reading and extraction
  Supports verification-code extraction, link extraction, and raw message viewing
- Mail pool orchestration
  Supports claiming, releasing, completing, cooldown recovery, and stale-claim recycling; long-lived mailboxes support project-scoped success reuse: same-project claims are blocked by recorded success history, and `success` returns the mailbox to `available` for immediate reuse by other projects; requests without `project_key` and `provider=cloudflare_temp_mail` / temp-mail accounts keep the legacy behavior
- Controlled external APIs
  Supports `X-API-Key` authentication, multiple consumer keys, mailbox scope restrictions, IP allowlists, and rate limits
- Notification delivery
  Supports business email notifications, Telegram push, and test sending
- Demo-site protection
  Supports locking the login-password change entry through environment variables so visitors cannot change the backend password from Settings

## Project Layout

```text
outlook_web/          Main Flask application (controllers / routes / services / repositories)
templates/            Page templates
static/               Frontend scripts and styles
data/                 SQLite data and runtime files
tests/                Automated tests
web_outlook_app.py    Backward-compatible entrypoint
```

## Quick Start

### Docker Deployment

**Option 1: docker run (quick start)**

```bash
docker run -d \
  --name outlook-email-plus \
  -p 5000:5000 \
  -v $(pwd)/data:/app/data \
  -e SECRET_KEY=your-secret-key-here \
  -e LOGIN_PASSWORD=your-login-password \
  -e ALLOW_LOGIN_PASSWORD_CHANGE=false \
  guangshanshui/outlook-email-plus:latest
```

**Option 2: docker-compose (recommended, includes one-click update)**

Save the following as `docker-compose.yml`, then run `docker-compose up -d`:

```yaml
services:
  app:
    image: ghcr.io/zeropointsix/outlook-email-plus:latest   # Recommended (more stable in some regions)
    # image: guangshanshui/outlook-email-plus:latest         # Docker Hub alternative
    container_name: outlook-email-plus
    restart: unless-stopped
    ports:
      - "5001:5000"           # Change to 5000:5000 or any other port
    env_file:
      - .env
    environment:
      SECRET_KEY: "${SECRET_KEY:?Set SECRET_KEY in .env}"
      # One-click update token: leave empty to use the built-in default;
      # for production, set a random strong password
      WATCHTOWER_HTTP_API_TOKEN: "${WATCHTOWER_HTTP_API_TOKEN:-outlook-mail-plus-watchtower-default}"
      # Docker API self-update (optional, advanced)
      # ⚠️ Enabling this allows the container to control other containers via Docker API
      # DOCKER_SELF_UPDATE_ALLOW: "false"
    volumes:
      - ./data:/app/data
      # Docker socket mount (optional, only for Docker API self-update)
      # ⚠️ Mounting docker.sock grants the container full Docker API access
      # - /var/run/docker.sock:/var/run/docker.sock
    labels:
      - "com.centurylinklabs.watchtower.enable=true"
    networks:
      - outlook-net

  watchtower:
    image: containrrr/watchtower
    container_name: watchtower
    restart: unless-stopped
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
    environment:
      - WATCHTOWER_HTTP_API_TOKEN=${WATCHTOWER_HTTP_API_TOKEN:-outlook-mail-plus-watchtower-default}
      - WATCHTOWER_HTTP_API_UPDATE=true
      - WATCHTOWER_CLEANUP=true
      - WATCHTOWER_HTTP_API_PERIODIC_POLLS=false
    command: --http-api-update --label-enable
    labels:
      - "com.centurylinklabs.watchtower.enable=false"
    networks:
      - outlook-net

networks:
  outlook-net:
    driver: bridge
```

Notes:

- Always mount `data/` to avoid losing the database and runtime data
- `SECRET_KEY` must stay stable and strong; generate a random 64-char value: `python -c "import secrets; print(secrets.token_hex(32))"`
- `WATCHTOWER_HTTP_API_TOKEN` **can be left empty** — both app and watchtower will automatically use the same built-in default, making one-click update work out of the box; for production, use a random strong password
- Once configured, the UI will show an update banner when a new version is detected; click "Update Now" to upgrade
- One-click update **only works with docker-compose deployment**; `docker run` single-container mode is not supported

**Update Methods**: Watchtower is the default (recommended). To use Docker API self-update (no Watchtower required), you need to:
1. Uncomment `DOCKER_SELF_UPDATE_ALLOW` and set it to `"true"`
2. Uncomment the docker.sock volume mount
3. Switch "Update Method" to "Docker API" in Settings
4. ⚠️ Please fully understand the security implications before enabling

#### ClawCloud / Reverse Proxy Deployment Notes

- Point health checks explicitly to `GET /healthz`. Do not rely on `/`, `/login`, or a 302 redirect chain; in this project, `/` is login-protected and redirects to `/login`
- `no healthy upstream` means the reverse proxy currently has no healthy backend. It does **not** automatically mean the app code crashed; after an update, check the **new container startup logs** and platform events first
- If platform events show `Stopping container`, `FailedKillPod`, or `KillPodSandbox DeadlineExceeded`, the incident includes a platform-side Pod stop/reclaim problem and should not be diagnosed from app logs alone
- This project uses SQLite with a persistent volume by default. During updates, keep it as a **single-instance** deployment; if old and new instances touch the same database file briefly, startup migrations or file-lock waits may cause health-check timeouts
- Treat `TEMP_EMAIL_UPSTREAM_READ_FAILED` separately from `no healthy upstream`: the former is a temp-mail upstream read failure, while the latter means the ingress layer has no healthy app instance behind it

### Local Run

```bash
python -m venv .venv
pip install -r requirements.txt
python web_outlook_app.py
```

### Run Tests

```bash
python -m unittest discover -s tests -v
```

## Common Environment Variables

- `SECRET_KEY`
  Required for session security and sensitive-data encryption
- `LOGIN_PASSWORD`
  Initial backend login password; after first startup it is hashed and stored in the database
- `ALLOW_LOGIN_PASSWORD_CHANGE`
  Whether login password changes are allowed in Settings. For demo sites, set this to `false`
- `DATABASE_PATH`
  SQLite database path. Default: `data/outlook_accounts.db`
- `PORT` / `HOST`
  Web server bind address
- `SCHEDULER_AUTOSTART`
  Whether background scheduler jobs start automatically
- `OAUTH_TOOL_ENABLED`
  Enables or disables the OAuth token tool entry and related APIs, default `true`
- `OAUTH_CLIENT_ID`
  Outlook OAuth application ID
- `OAUTH_CLIENT_SECRET`
  Must remain empty in compatibility mode; Azure apps that require a `client_secret` are outside the supported contract
- `OAUTH_REDIRECT_URI`
  Outlook OAuth callback URL
- `OAUTH_SCOPE`
  Backend environment default scope (fallback): `offline_access https://outlook.office.com/IMAP.AccessAsUser.All`; frontend first-render default uses Graph preset
- `OAUTH_TENANT`
  Default tenant for the token tool, fixed to compatibility-mode `consumers`
- `GPTMAIL_BASE_URL`
  GPTMail service URL
- `GPTMAIL_API_KEY`
  GPTMail API key for temp-mail capabilities

### One-Click Update

- `WATCHTOWER_HTTP_API_TOKEN`
  Watchtower API auth token. **Can be left empty** — both app and watchtower automatically use the same built-in default, making it work out of the box; for production, use a random strong password
- `WATCHTOWER_API_URL`
  Watchtower API address, default `http://watchtower:8080` (Docker internal network, usually no need to change)
- `DOCKER_SELF_UPDATE_ALLOW`
  Whether to enable Docker API self-update, default `false`. ⚠️ Grants container Docker API access when enabled
- `DOCKER_IMAGE`
  Current container image name (optional, for deployment info detection)

> **Security Note**: Docker API self-update requires mounting `/var/run/docker.sock`, which grants full Docker API access to the container. For production environments, Watchtower is recommended.

## Notification Channels

### Email Notifications

If you want to enable business email notifications, you need to configure SMTP separately. Email notifications, Telegram, and GPTMail are independent channels and do not replace each other.

Minimum required variables:

- `EMAIL_NOTIFICATION_SMTP_HOST`
- `EMAIL_NOTIFICATION_FROM`

Common optional variables:

- `EMAIL_NOTIFICATION_SMTP_PORT`
- `EMAIL_NOTIFICATION_SMTP_USERNAME`
- `EMAIL_NOTIFICATION_SMTP_PASSWORD`
- `EMAIL_NOTIFICATION_SMTP_USE_TLS`
- `EMAIL_NOTIFICATION_SMTP_USE_SSL`
- `EMAIL_NOTIFICATION_SMTP_TIMEOUT`

Example:

```env
EMAIL_NOTIFICATION_SMTP_HOST=smtp.qq.com
EMAIL_NOTIFICATION_SMTP_PORT=465
EMAIL_NOTIFICATION_FROM=your_account@qq.com
EMAIL_NOTIFICATION_SMTP_USERNAME=your_account@qq.com
EMAIL_NOTIFICATION_SMTP_PASSWORD=your_smtp_auth_code
EMAIL_NOTIFICATION_SMTP_USE_SSL=true
EMAIL_NOTIFICATION_SMTP_USE_TLS=false
EMAIL_NOTIFICATION_SMTP_TIMEOUT=15
```

Notes:

- the Settings page follows a save-first-then-test flow
- the test endpoint does not read temporary values from the form
- the system only uses the saved `email_notification_recipient`

### Telegram Push

The Settings page supports:

- `telegram_bot_token`
- `telegram_chat_id`
- `telegram_poll_interval`

In the current version, Telegram push and business email notifications are both handled by the unified notification-dispatch flow.

## External API and Mail Pool Integration

If you want to connect this project to registration workers, script platforms, or other automation systems, the recommended path is the controlled external API:

- path prefix: `/api/external/*`
- auth header: `X-API-Key`
- mail-pool endpoints: `/api/external/pool/*`

Current external API capabilities include:

- single-key authentication
- multi-key configuration
- mailbox scope restrictions per caller
- public-mode allowlists and rate limits
- the ability to disable risky endpoints such as raw-content reading and long polling

Notes:

- the old anonymous `/api/pool/*` endpoints have been removed
- in production, controlled public mode with allowlists is recommended

## Browser Extension

The `browser-extension/` directory contains a companion Chrome / Edge extension (Manifest V3). It provides a one-stop panel for the full claim → verification → complete/release flow without switching tabs.

Full usage guide: [browser-extension/README.md](./browser-extension/README.md)

### Project Key

The project key enables **multi-tenant isolation** in the mail pool — different projects' claims are kept separate. Combined with `caller_id + task_id`, it also prevents duplicate assignments within the same project.

- **Omit**: claim from the shared public pool
- **Set**: claim only from that project's mailboxes; after a `success` complete, the mailbox returns to `available` immediately and can be reused by other projects

### Complete vs Release

Both operations end the current task; the difference is what happens to the mailbox:

| Operation | Mailbox status | When to use |
|-----------|---------------|-------------|
| **Release** | → `available` (claimable again immediately) | Registration failed, wrong mailbox, test return |
| **Complete** | → `used` (marked used, not re-assigned by default) | Registration succeeded, verification code consumed |

> When project reuse is enabled, `complete(result=success)` with an explicit `project_key` returns the mailbox directly to `available` for cross-project reuse.

## Demo Site Recommendation

If you want to expose a demo site to other users, at minimum use:

```env
LOGIN_PASSWORD=your-strong-password
ALLOW_LOGIN_PASSWORD_CHANGE=false
```

- the site remains usable
- visitors cannot change the backend login password from Settings

## Project Documentation

- [中文注册与邮箱池接口文档](./注册与邮箱池接口文档.md)
- [Registration Worker and Mail Pool API](./registration-mail-pool-api.en.md)

If you plan to integrate registration workers or batch workflows, start with the mail-pool and external API docs.

## Acknowledgements

This project is built on:

- Flask
- SQLite
- Microsoft Graph API
- IMAP
- APScheduler

It also draws ideas from:

- [assast/outlookEmail](https://github.com/assast/outlookEmail)
- [gblaowang-i/MailAggregator_Pro](https://github.com/gblaowang-i/MailAggregator_Pro)

## License

Apache License 2.0

## Contact

For project-related issues or collaboration opportunities, feel free to reach out via email: [outlookmailplus@163.com](mailto:outlookmailplus@163.com)

