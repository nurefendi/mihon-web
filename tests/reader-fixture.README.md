# Portable isolated reader fixture

`setup-reader-fixture.py` generates **test data only**: the original two 64×96
technical PNG pages in `001.cbz`, plus `runtime-test.env`. It never connects to
an engine or database, provisions containers, or changes production data.
**Never use the generated credentials or config for production.**

Use Python 3 with `bcrypt` installed in a disposable test environment. The
lightweight `reader-fixture` GitHub Actions job installs `bcrypt==4.3.0` in its
own virtualenv and runs the offline unit regressions. Existing Go/MariaDB, UI,
Chromium and runtime-image CI gates remain in place. Do not run suites/builds
on the production host.

## Choose and reuse an output directory

From a clean operator checkout or CI runner (not a live production checkout):

```sh
python3 tests/setup-reader-fixture.py --output-dir "$PWD/test-artifacts/reader"
# Or share the same path with both scripts:
export MIHON_FIXTURE_DIR="$PWD/test-artifacts/reader"
python3 tests/setup-reader-fixture.py
```

Without `--output-dir` or `MIHON_FIXTURE_DIR`, the generator creates a **unique**
private `mihon-reader-fixture-*` directory using Python's temporary-directory
selection (`TMPDIR` supported). Standard output contains only the absolute
chosen directory, so it can be captured for subsequent steps:

```sh
export MIHON_FIXTURE_DIR="$(python3 tests/setup-reader-fixture.py)"
# Provision isolated containers and mount/copy "$MIHON_FIXTURE_DIR/001.cbz"
# into the engine's labelled __Integration_fixture_NOT_CONTENT local source.
# Configure the isolated app with "$MIHON_FIXTURE_DIR/runtime-test.env".
# Only AFTER provisioning those disposable integration containers:
python3 ops/reader-integration.py --fixture-dir "$MIHON_FIXTURE_DIR"
```

The integration consumer requires existing `mihon-engine-test`, `mihon-db-test`
and `mihon-web-integration` containers, `requests`, Playwright and Chromium.
It is **not** part of the offline unit job: it mutates the isolated test DB and
library. It refuses a missing fixture directory or non-loopback public origin,
and retains its `mihon-db-test` database guard. Screenshots now go to
`$MIHON_FIXTURE_DIR/visual/reader-isolated-fixture.png`, not a server home path.
A custom DB hostname accepted by the offline generator does **not** retarget
this guarded consumer's Docker DB command.

## Explicit runtime overrides

CLI flags take precedence over **fixture-prefixed** environment variables;
ordinary application variables such as `MYSQL_DSN` are deliberately ignored.
Only set these to endpoints belonging to your disposable test stack:

| CLI | Environment variable | Isolated default |
| --- | --- | --- |
| `--output-dir` | `MIHON_FIXTURE_DIR` | Unique temporary directory |
| `--mysql-dsn` | `MIHON_FIXTURE_MYSQL_DSN` | `mihon_test:isolated-test-only@tcp(mihon-db-test:3306)/mihon_test?parseTime=true` |
| `--public-origin` | `MIHON_FIXTURE_PUBLIC_ORIGIN` | `http://127.0.0.1:18085` |
| `--engine-url` | `MIHON_FIXTURE_ENGINE_URL` | `http://mihon-engine-test:4567` |
| `--listen-addr` | `MIHON_FIXTURE_LISTEN_ADDR` | `:8080` |

Bootstrap username/password remain `admin` /
`isolated-browser-integration-only`, for **isolated testing only**. Each run
creates a fresh bcrypt hash; the CBZ bytes remain deterministic. Multiline,
NUL-containing and empty runtime values are rejected to prevent env injection.
Do not shell-source the generated env file: it is an application/Docker env
file, and the bcrypt value contains literal dollar signs.

The chosen directory is restricted to mode `0700`; both generated files are
atomically replaced with mode `0600`, including when reusing an existing
fixture directory. Final directory/file symlinks are rejected. Only these two
fixture files are replaced; unrelated files are not removed and no cleanup of
arbitrary paths is performed. The temporary-directory default is retained for
the caller to consume and later remove deliberately. Never choose a production
data/config directory, or a directory shared with an untrusted writer.

`--help` and importing the generator require no bcrypt installation and create
no fixture files. Regression coverage includes nested/relative/temp paths,
CLI/env precedence, isolated defaults and overrides, exact decoded pixels,
repeatable CBZ bytes, private modes, safe rewrites, and no import-time I/O.
This is a focused fixture change, not an audit of all repository host paths.
