# MediPos

Pharmacy / medical store ERP: point of sale, batch inventory with FEFO, purchasing, suppliers,
smart reorder alerts, double-entry accounts and reports. One repository, three apps:

| Folder | What it is | Stack |
| --- | --- | --- |
| [`backend/`](backend) | The API and every business rule | Django 5.2, Django REST Framework, PostgreSQL, Celery + Redis |
| [`frontend/`](frontend) | Web app: POS, inventory, purchasing, reports, accounts | Next.js 16 (App Router), TypeScript, Tailwind |
| [`phone/`](phone) | Mobile app: stock alerts, order list, barcode scan, batch look-up | React Native, Expo SDK 58, TypeScript |

The web and phone apps hold no business logic. Prices, tax, discounts limits, stock deduction and
permissions are decided by the API; the clients display what it returns.

**What is built and what is not:** see [`docs/STATUS.md`](docs/STATUS.md). The original requirements are in
[`docs/requirements.md`](docs/requirements.md) and the API contract in [`docs/openapi.yaml`](docs/openapi.yaml)
(live at `/api/docs/` when the backend runs).

Deployment, including the web app on Vercel with the API behind a tunnel, is in
[`docs/DEPLOY.md`](docs/DEPLOY.md).

## Run everything with Docker

```bash
cp .env.example .env          # set DJANGO_SECRET_KEY and POSTGRES_PASSWORD at least
docker compose up -d --build
docker compose exec backend python manage.py createsuperuser   # your owner account
docker compose exec backend python manage.py seed_demo         # optional demo medicines and stock
```

Web app on http://localhost:3000, API on http://localhost:8000. For plain-HTTP local use set
`SECURE_SSL_REDIRECT=0`, `DJANGO_ALLOWED_HOSTS=localhost`, `CORS_ALLOWED_ORIGINS=http://localhost:3000`
and `NEXT_PUBLIC_API_URL=http://localhost:8000` in `.env`.

The stack is `db` (PostgreSQL 16), `redis`, `backend` (gunicorn, runs migrations on start), `worker` and
`beat` (Celery), `frontend`, and `backup` (daily `pg_dump`).

### Hosting the pieces separately

The web app is a pure client — every page runs in the browser and nothing is fetched at build time —
so it deploys to **Vercel** with Root Directory `frontend` and the `NEXT_PUBLIC_*` variables, while
the API runs wherever the database is. To serve the API from your own machine, which has no fixed
IP, put a **Cloudflare Tunnel** in front of it:
`docker compose --profile tunnel up -d cloudflared`. Both are covered step by step, with the
alternatives, in [`docs/DEPLOY.md`](docs/DEPLOY.md).

### Coolify

Create a **Docker Compose** resource from this repository, paste the variables from `.env.example`, and
give `frontend` and `backend` their domains (ports 3000 and 8000). `NEXT_PUBLIC_API_URL` is compiled
into the web app, so redeploy the frontend after changing it. Both services expose health checks
(`/api/health/` and `/login`).

## Local development

**Backend**

```bash
cd backend
python -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env && set -a && . ./.env && set +a
python manage.py migrate
python manage.py seed_demo --owner admin --password '<choose a password>'
python manage.py runserver
pytest                              # needs PostgreSQL for the concurrency test
```

Without `REDIS_URL` Celery tasks run inline, so the backend works with only PostgreSQL.

**Frontend**

```bash
cd frontend
cp .env.example .env.local
npm install
npm run dev                         # http://localhost:3000
```

**Phone**

```bash
cd phone
cp .env.example .env                # EXPO_PUBLIC_API_URL: your machine's LAN address for a real device
npm install
npx expo start
```

Camera scanning and push notifications need a development build (`npx expo run:android`), not Expo Go.
For push: create a Firebase project, put `google-services.json` in `phone/` and reference it from
`app.json` (`android.googleServicesFile`), and give the backend the service-account JSON through
`FIREBASE_CREDENTIALS_FILE`. Without it the app and API work normally and notifications stay in-app.

## How the critical rules are enforced

| Rule | Where |
| --- | --- |
| Only posted documents change stock; every change writes a ledger row | `backend/apps/inventory/services.py` (`_post`); `StockMovement` rows cannot be updated or deleted |
| FEFO (or FIFO) deduction, never from expired / blocked batches | `issue_stock`, `sellable_batches` |
| No negative stock, no overselling under concurrency | row locks (`select_for_update`) plus a database `CHECK (quantity_on_hand >= 0)` |
| Purchase orders never add stock; a confirmed GRN adds it exactly once | `backend/apps/purchases/services.py` (`confirm_grn` locks the GRN and is a no-op the second time) |
| Sales are atomic and safe to retry | `backend/apps/sales/services.py` (`create_sale`, `Idempotency-Key` header, unique constraint) |
| Returns reference the original invoice and go back to the original batches | `create_sale_return` |
| Posted accounting entries are reversed, never edited | `backend/apps/accounting/` (`JournalEntry` is immutable; `reverse_entries`) |
| Profit uses actual batch cost | sale lines store the cost of the batches they were served from |
| Money is `Decimal` end to end | models, `apps/common/money.py`; the API sends decimals as strings |
| Role and branch permissions are checked on the server | `apps/accounts/permissions.py`, `apps/common/api.py` (`X-Branch-Id` header) |
| Low-stock alerts fire once and reset when stock recovers | `apps/notifications/services.py` (`evaluate_stock_level`, partial unique constraint) |

Each of these has a test in `backend/tests/`.

## Roles

Owner, Branch Admin, Pharmacist, Cashier, Inventory Manager, Purchase Officer, Accountant, Auditor.
The permission each role has is defined in one place: `backend/apps/accounts/permissions.py`. Users
are assigned to branches; owners see all branches.

## Backups

The `backup` service writes a compressed dump to `./backups` every day and keeps 14 days
(`BACKUP_KEEP_DAYS`). Prove a backup restores:

```bash
docker compose run --rm --entrypoint /scripts/restore-test.sh backup
```

It restores the newest dump into a scratch database, compares row counts and checks the ledger still
balances. Copy `./backups` off the server; a backup on the same disk is not a backup.

## Continuous integration

`.github/workflows/ci.yml` runs on every push: backend tests on PostgreSQL, migration and deploy
checks, frontend lint/type-check/build, phone lint/type-check/Android bundle, and a Docker build that
waits for both health checks.
