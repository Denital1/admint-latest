# Production deployment

Configuration is prepared locally. No public deployment has been performed. A Linux Docker host and a real domain are needed to run this stack. PostgreSQL, Redis and the backend have no published host ports; Caddy exposes only HTTP/HTTPS.

## Configure and start

From the repository root on the server:

```sh
python3 deploy/configure.py YOUR_REAL_DOMAIN
docker compose --env-file deploy/.env.production -f deploy/compose.yml config --quiet
docker compose --env-file deploy/.env.production -f deploy/compose.yml up --build -d
docker compose --env-file deploy/.env.production -f deploy/compose.yml ps
docker compose --env-file deploy/.env.production -f deploy/compose.yml logs --tail=100 migrate backend proxy backup
```

The generator writes private random application and database secrets, and refuses to overwrite existing configuration. Do not commit or share `.env.production`; `.env.production.example` contains placeholders that must not be used as credentials. Use URL-safe database passwords in this Compose configuration. Keep this file when redeploying: changing the PostgreSQL password environment variable does not change an initialized database's password.

Point the domain's DNS record at the host and allow TCP 80/443. Caddy manages HTTPS certificates. The migration service waits for PostgreSQL/Redis readiness, rejects unsafe production settings, applies migrations and collects admin static files. Backend starts after successful migration. On a later release, recreate the migration job before restarting application services:

```sh
docker compose --env-file deploy/.env.production -f deploy/compose.yml build
docker compose --env-file deploy/.env.production -f deploy/compose.yml run --rm migrate
docker compose --env-file deploy/.env.production -f deploy/compose.yml up -d
docker compose --env-file deploy/.env.production -f deploy/compose.yml exec backend python manage.py createsuperuser
```

Never expose backend/database/cache ports publicly. PostgreSQL initializes a separate non-superuser application role; only the database container receives the administrator password. The backend and backup service receive application credentials. Initialization scripts run only on a new database volume. Caddy overwrites `X-AdMint-Client-IP` with the socket client address; production Django trusts that header for rate limits. The local development settings ignore it. Add trusted CDN proxy handling only when that infrastructure is explicitly configured. Redis is private to this Compose stack and shares rate limits across backend workers; it does not store user sessions. Sessions, uploads, order evidence and all marketplace records are stored in PostgreSQL.

## Existing local data

The production PostgreSQL volume initially contains no local users or purchases. Keep the local SQLite database and its consistent backups. Copying a SQLite file into a PostgreSQL volume does not migrate it. Before importing real data, rehearse Django `dumpdata`/`loaddata` against a staging database, excluding content types and auto-created permissions, verify foreign keys/account identities, record counts, order files and purchase signatures, then plan a maintenance window and private export. Do not use test fixtures as production purchases. No local data migration has been performed by this preparation.

## Backups and restore drill

The backup service makes a consistent PostgreSQL custom-format dump immediately and every 24 hours. Dumps are written privately to a temporary file, checked with `pg_restore --list`, then renamed only on success. The health check fails if no recent successful dump exists. No automatic retention deletion is configured. These same-host copies still need private off-server storage and a retention policy before public launch.

Create a manual dump and export it privately:

```sh
docker compose --env-file deploy/.env.production -f deploy/compose.yml run --rm backup sh /backup-postgres.sh --once
docker compose --env-file deploy/.env.production -f deploy/compose.yml exec backup ls -l /backups
docker compose --env-file deploy/.env.production -f deploy/compose.yml cp backup:/backups/CHOSEN_FILE.dump ./CHOSEN_FILE.dump
```

Rehearse restoration into a **new isolated staging database**, not the live database:

```sh
docker compose --env-file deploy/.env.production -f deploy/compose.yml exec database createdb -U admint_admin -O admint admint_restore_check
docker compose --env-file deploy/.env.production -f deploy/compose.yml cp ./CHOSEN_FILE.dump database:/tmp/restore-check.dump
docker compose --env-file deploy/.env.production -f deploy/compose.yml exec database pg_restore --exit-on-error --no-owner --no-acl --role=admint -U admint_admin -d admint_restore_check /tmp/restore-check.dump
```

Verify table counts, login and order history on a staging application pointed at this new database. A live restoration requires a maintenance window with application writers stopped and a verified backup of the current database; do not run `pg_restore --clean` against production as a first experiment. Backups include private profiles, messages and uploaded images; restrict access and encrypt exported/off-server copies.

## Release verification

Run `python manage.py check --deploy --fail-level WARNING` in the backend container. Verify HTTPS redirects, secure session/CSRF cookies, admin CSS, login, CSRF rejection, private order/file permissions, database readiness and backup health. Repeat a user-approved Devnet purchase and fulfillment cycle on staging. Mainnet payment validation and a mainnet release are separate work; this preparation does not assert mainnet readiness. Configure external uptime/error monitoring and rehearse restoring a backup before public users.

Google OAuth remains optional: create a Web client with redirect URI `https://YOUR_REAL_DOMAIN/api/auth/google/callback/`, set its credentials privately, and restart backend. No external OAuth provider was configured here.

Current purchases pay the seller directly. Refund requests do not transfer funds and there is no escrow. Admin moderation is available at `/admin/`. Private order messages poll while visible; no email/push delivery or end-to-end encryption is claimed.

References: [Django deployment checklist](https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/), [Caddy proxy headers](https://caddyserver.com/docs/caddyfile/directives/reverse_proxy), [official PostgreSQL image](https://hub.docker.com/_/postgres).
