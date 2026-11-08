# Mihon Web

An independent web reading interface inspired by Mihon. The Go application serves HTML/CSS/JavaScript directly, without a Node.js frontend build. **This is not an official Mihon project**, and it does not yet have full feature parity. See [ROADMAP.md](ROADMAP.md) and [VERIFICATION.md](VERIFICATION.md).

## Architecture

```text
Browser → Vercel HTTPS rewrite/proxy → HTTPS origin server → Go (Mihon Web)
                                                  ├─ MariaDB: users, sessions, preferences
                                                  └─ Suwayomi: library, extensions, downloads (persistent H2 volume)
```

**Vercel is the HTTPS entry point, not the host for the entire application.** This repository contains a long-running Go server that needs MariaDB and a Suwayomi/JVM engine with persistent storage. Running `vercel deploy` alone will not start those services. Provide an always-on origin server (such as a VPS) with its own HTTPS URL reachable from Vercel. Do not expose the Suwayomi or MariaDB ports publicly.

The initial setup has one administrator and one shared library; it is not isolated multi-user hosting. Suwayomi does not use MariaDB for its library: that data lives in the engine's H2 volume. KCEF is disabled in `compose.yaml`, so sources requiring Chromium/WebView may not work.

## Sources and extensions

There is no default third-party extension repository. After signing in, add only repositories you trust under Browse → Extensions. Explicitly allow their URLs through `TRUSTED_REPOSITORY_URLS`; repository metadata and APKs are third-party code used by the engine.

## Deploy with Vercel as a proxy

### 1. Set up persistent services on the origin server

You need Docker Compose, MariaDB, and an HTTPS domain for the origin server (for example, `https://origin.example.com`). `compose.yaml` expects external `quiz-net` (MariaDB) and `npm-net` (reverse proxy) networks; adapt the networks and database host for your infrastructure. Scripts in `ops/` and some Compose defaults are specific to an existing deployment: **check embedded paths, container names, and domains before running them**.

1. Create a dedicated MariaDB schema and user named `mihon_web` with the application's required privileges (SELECT, INSERT, UPDATE, DELETE, CREATE, ALTER, INDEX, REFERENCES). Do not reuse another application's database account. Example DSN: `mihon_web:<password>@tcp(<db-host>:3306)/mihon_web?parseTime=true&charset=utf8mb4`.
2. Create a private credentials directory outside the repository. Generate an administrator password, store it securely, and create a bcrypt hash (for example, using Python's `bcrypt` package). Put the following settings in `runtime.env` with file permissions `0600`:

   ```dotenv
   MYSQL_DSN=mihon_web:<password>@tcp(<db-host>:3306)/mihon_web?parseTime=true&charset=utf8mb4
   PUBLIC_ORIGIN=https://manga.example.com
   ENGINE_URL=http://mihon-engine:4567
   BOOTSTRAP_USERNAME=admin
   BOOTSTRAP_PASSWORD_HASH=<bcrypt-hash>
   LISTEN_ADDR=:8080
   TRUSTED_REPOSITORY_URLS=
   ```

   `PUBLIC_ORIGIN` must match the public Vercel URL used by the browser **exactly**, without a trailing slash. It is not the origin server URL: login checks the request Origin for CSRF protection, and cookies are marked Secure for HTTPS. Never commit `runtime.env` or the administrator password. Set `TRUSTED_PROXY_CIDRS` only if a trusted proxy **overwrites**, rather than forwards, the `X-Mihon-Client-IP` header; otherwise leave it unset.
3. Create the networks and volume required by `compose.yaml` (for example, `docker network create mihon-net` and `docker volume create mihon-engine-data`). Ensure the database and proxy networks also exist, or adapt Compose to your infrastructure. From the repository root, run:

   ```sh
   docker build -t mihon-web:local .
   MIHON_RUNTIME_ENV=/secure/path/runtime.env docker compose up -d
   docker compose ps
   curl -f http://127.0.0.1:8084/healthz
   ```

4. Configure a TLS reverse proxy on the origin server to forward `https://origin.example.com/*` to `http://127.0.0.1:8084/*` without altering paths, methods, bodies, cookies, or the `Origin` header. Restrict direct access to the origin where feasible while keeping it reachable from Vercel. Use a valid TLS certificate. Do not apply `ops/mihon-web.nginx.conf` unchanged: it is specific to a previous deployment. Keep Go authentication enabled and the engine private.

### 2. Configure the Vercel project

Add a `vercel.json` file at the repository root, replacing the example URL with your origin server's HTTPS domain:

```json
{
  "rewrites": [
    { "source": "/:path*", "destination": "https://origin.example.com/:path*" }
  ]
}
```

Import the repository into Vercel as an **Other** project, without a frontend build command or output directory. The rewrite forwards pages, assets, and API requests to the Go server. Deploy from the Vercel dashboard or run `vercel --prod` after linking the project. Add your public domain (for example, `manga.example.com`) under Settings → Domains and configure DNS as instructed by Vercel. Set `PUBLIC_ORIGIN` on the **origin server** to `https://manga.example.com` before trying to log in; it does not need to be a Vercel environment variable because Go does not run there. Preview URLs have a different origin and will not pass login/CSRF checks without separate configuration.

Check `https://manga.example.com/healthz`, open the login page, and sign in with the administrator password you stored privately. Verify login and API requests through the Vercel domain, not only through the origin server. The Vercel rewrite still depends on the origin server's availability and may be subject to Vercel request time or size limits, especially for large uploads or downloads. An origin server accessible directly still needs application authentication; a rewrite is not an origin access control mechanism.

## Tests

- `go test -count=1 ./...`
- `go test -race -count=1 ./...` and `go vet ./...`
- `MYSQL_TEST_DSN=<separate-test-schema-DSN> go test -count=1 ./...` for MariaDB integration tests; never use a production database.
- UI and contract tests are under `tests/`.

## Backups and rollback

Back up **both the dedicated MariaDB schema and the `mihon-engine-data` volume**. An engine library export is not a replacement for a full volume backup. Stop the engine or take a consistent snapshot before copying H2 files. Keep credentials secure, outside the repository and public backups. Roll back a Go image only if its database schema is still compatible; back up engine data before upgrading Suwayomi because downgrading its database may be unsafe.

## Acknowledgements

UI and behavior reference: [Mihon](https://github.com/mihonapp/mihon) (Apache-2.0). Android extension compatibility: [Suwayomi](https://github.com/Suwayomi/Suwayomi-Server), distributed under its own license. This project is not an official product of either project.
