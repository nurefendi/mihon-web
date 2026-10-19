# Mihon Web

Independent, authenticated web rewrite of Mihon's reading experience, targeting feature parity incrementally. Go serves locally bundled HTML/CSS/JavaScript; **no Node.js, npm, SPA framework or frontend build step is needed at runtime**.

**Not an official Mihon project.** The first release is not complete feature parity. See [ROADMAP.md](ROADMAP.md) and [VERIFICATION.md](VERIFICATION.md) for actual scope and test evidence.

## Architecture

```
browser → mg.namiza.id / HTTPS → Go web service
                                    ├─ MariaDB: mihon_web only (users, sessions, UI preferences)
                                    └─ private Suwayomi compatibility engine
                                         └─ persistent H2 library/extensions/download data
```

Go is the web application; Suwayomi is a separate JVM/Android-extension compatibility engine, **not a Go port of APK execution**. Its private API has no published host port. The existing Quiz Web service, schema and user are not reused or modified; only the existing MariaDB server is shared. Library/reading data is in the engine's H2 volume, **not MariaDB**: Suwayomi does not support MariaDB.

The initial deployment has a single administrator and **one shared manga library**. It is not isolated multi-user hosting. Engine KCEF is disabled for the small VPS; sources needing Chromium/WebView login/challenges may not work. Do not assume all extensions work identically to Android.

## Sources and extensions

Neither Mihon nor Suwayomi includes a default third-party repository. A fresh installation has the built-in local source only. In Browse → Extensions, add the same repository you explicitly trust in your Mihon application, then install the extensions you use. Repository URLs/APKs are executable third-party code; this is an administrator-only capability, not an unauthenticated scraper endpoint. There is no automatic installation of an invented “Mihon default” source.

## Run / deployment

Requirements: Docker/Compose, existing `quiz-net` / `npm-net` networks (or edit the Compose network definitions), reachable MariaDB and a TLS reverse proxy. `compose.yaml` is the deployment specification. The official engine is pinned by digest; changing it needs contract/regression tests.

1. Provision a new application schema/user. On this host, `python3 ops/provision-db.py` provisions **only** `mihon_web` with scoped grants using the existing `mariadb-quiz` container. It writes private credentials to `/home/mazaya/mihon-web-deploy/database.env`, mode 0600, preserving them across retries. Do not use the production Quiz Web DB account.
2. Run `python3 ops/init-credentials.py` with Python `bcrypt` installed. It creates the one-time private `admin-password` file and runtime.env outside the repository. Passwords are bcrypt-hashed in runtime.env and in the application's user table; never commit these files. This script does not rotate an existing account's password.
3. Create the isolated resources once: `docker network create mihon-net` and `docker volume create mihon-engine-data` (skip if already present).
4. Build the tested image: `docker build -t mihon-web:local .`. The Docker build runs Go tests/vet before compiling and the runtime is non-root/read-only.
5. Deploy: `docker compose up -d`. The Go app runs only on host loopback `127.0.0.1:8084`; the engine has no host port. Verify `docker compose ps` and `curl http://127.0.0.1:8084/healthz`.
6. Configure the reverse proxy using `ops/mihon-web.nginx.conf`, issue a valid certificate for your domain, validate Nginx before reloading and verify the public HTTPS origin. This host's file is deployment-managed under NPM's `temp/`, not an NPM UI database entry.

Environment keys (private runtime.env; Compose uses `env_file.format: raw` to preserve bcrypt `$` characters):

- `MYSQL_DSN`: `mihon_web:<private-password>@tcp(mariadb-quiz:3306)/mihon_web?parseTime=true&charset=utf8mb4`
- `PUBLIC_ORIGIN`: `https://mg.namiza.id` (exact origin; CSRF validation uses it)
- `ENGINE_URL`: `http://mihon-engine:4567` (private only)
- `BOOTSTRAP_USERNAME`: `admin`
- `BOOTSTRAP_PASSWORD_HASH`: bcrypt hash, not plaintext
- `LISTEN_ADDR`: `:8080`
- `TRUSTED_PROXY_CIDRS`: exact trusted NPM peer CIDR(s), comma-separated; on this deployment `172.18.0.5/32`. Empty means forwarding headers are ignored. NPM overwrites `X-Mihon-Client-IP` after validating Cloudflare's peer ranges; arbitrary X-Forwarded-For/X-Real-IP are never trusted by Go. Recheck the pinned peer after replacing NPM.
- `TRUSTED_REPOSITORY_URLS`: comma-separated **exact** repository URLs approved by the server operator. Empty means repository addition is disabled. This is an explicit trust boundary, not a network sandbox: the configured publisher and its recursive repository metadata/APK code are trusted to initiate engine-side requests. Do not add an untrusted URL merely because it resolves publicly. Broken/expired repositories can still be removed without a DNS check.

Missing credentials/configuration fail closed. Do not disable authentication to work around setup errors. Auth cookies are HttpOnly, SameSite and Secure for HTTPS. All engine writes—including legacy GET actions—require CSRF; the browser is not given unrestricted access to engine configuration.

### Initial login

Open the public site and sign in as `admin`. Read the generated password **privately on the server** with `less /home/mazaya/mihon-web-deploy/admin-password`; do not paste it into a group chat or GitHub. Account/password management beyond the bootstrap administrator is a roadmap item.

### Tests / CI

- `go test -count=1 ./...`
- `go test -race -count=1 ./...` and `go vet ./...`
- `MYSQL_TEST_DSN=<isolated-test-schema-DSN> go test -count=1 ./...` for real MariaDB integration. Never point destructive integration tests at production.
- UI helper/contract tests are under `tests/`.
- GitHub Actions runs verification and a Docker build. It publishes text verification results to the `ci-status` Git branch so the VPS can read them over Git SSH without `gh` or a token. Match `source_sha` to the exact application commit; a stale green status is not proof of the current revision.

### Persistence / rollback

Back up **both** the dedicated MariaDB schema and `mihon-engine-data` volume (including extensions, library database and downloads). The engine's Mihon-compatible backup export is useful but is not a full volume/disaster-recovery backup. Stop the engine or use a consistent snapshot before copying H2 database files. Preserve runtime.env securely; never include it in public backups or source commits.

Roll back only the Go image if its schema remains backward-compatible. Keep previous images and back up engine data before engine upgrades; downgrading an engine after DB migration is not automatically safe. Compose only manages Mihon containers, not Quiz Web, NPM or shared MariaDB.

This host's dedicated user-systemd `mihon-web-cert-renew.timer` checks only the `mihon-web` certificate daily; the user has lingering enabled so the timer persists across logouts. Issuance/renewal config remains inside NPM's persistent letsencrypt bind mount. The deploy hook validates/reloads Nginx only after a successful renewal.

## Upstream acknowledgements

UI navigation/palette and behavior reference Mihon, licensed Apache-2.0: `https://github.com/mihonapp/mihon`. Android extension compatibility is provided by Suwayomi: `https://github.com/Suwayomi/Suwayomi-Server`; its separately distributed image retains its own license. Do not present this rewrite as upstream Mihon or a guarantee of upstream support.
