# orbit

A working model of a forward-authentication security proxy, built to learn the
disciplines rather than to ship a product.

Two services sit behind nginx:

- **`gate`** — an authentication service. It is not in the request path. nginx
  holds each incoming request and asks `gate` whether the caller is allowed
  through, then forwards the original request with identity headers attached.
- **`catalog`** — an ordinary business service, deliberately trivial. It serves a
  list of items and contains no security code at all.

Around them: a Python client, PostgreSQL persistence, Docker images, CI workflows,
and Helm charts for Kubernetes deployment.

## Quickstart

```bash
make install     # one virtualenv at .venv, both services editable
make help        # available commands, discovered services, missing tools
make test        # both suites; requires local PostgreSQL (see below)
```

Or bring up the whole stack — nginx on `:8080`, and nothing else reachable:

```bash
COMMIT=$(git rev-parse --short HEAD) docker compose up -d --build

curl -i localhost:8080/items         # 401 -- nginx asked gate, gate said no
curl -i localhost:8080/health/ready  # 200 -- catalog's, and public on purpose
curl -i localhost:5000/items         # connection refused, which is the point

docker compose down
```

A real login needs a provider: copy `apps/gate/.env.example` to `apps/gate/.env`.
The `.env` file holds the tenant values and is
gitignored, so a fresh clone comes up with a placeholder and a login that goes
nowhere. Configure the provider URL, client ID, client secret, and group claim
in that file to connect your own identity provider. Gate
[configuration defaults](apps/gate/gate/config.py) list the supported settings.

## Documentation

- [Token flow](docs/token-flow.html) — a visual explanation of provider tokens,
  Gate session tokens, and the authentication flow. Open the HTML file in a browser.
- [Helm configuration](deploy/helm/orbit/values.yaml) — chart defaults; layer the
  development or production values file and replace its placeholders to deploy.

## Running tests

Catalog tests require PostgreSQL and use a separate `orbit_test` database.
Start an isolated test server, then run both suites:

```bash
docker run -d --name orbit-test-postgres \
  -e POSTGRES_PASSWORD=orbit-dev \
  -p 127.0.0.1:55432:5432 postgres:18
# Wait until this reports "accepting connections":
docker exec orbit-test-postgres pg_isready -U postgres
DB_HOST=127.0.0.1 DB_PORT=55432 make test
docker rm -f orbit-test-postgres
```

The test fixtures reset tables in the test database; use a disposable database.
Gate tests mock the identity provider and require no provider credentials.

With Helm installed, check chart rendering and migration error handling:

```bash
.venv/bin/python -m unittest discover -s deploy/helm/tests -v
```
