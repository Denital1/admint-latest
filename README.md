# AdMint

AdMint is a Solana-powered marketplace for tokenized advertising rights. The frontend is built with Next.js/React/Tailwind, while the application backend is Django + Django REST Framework with persistent storage.

## Architecture

```text
Next.js / React / Tailwind
        │
        ├── Wallet Standard → Phantom / other Solana wallets
        │
        ├── Solana RPC → transaction signing + Ad Right minting
        │
        └── Django REST API → PostgreSQL / SQLite
                               ├── Listings
                               ├── Purchases
                               ├── Wallet profiles
                               └── Ad Rights
```

The wallet never sends a private key to Django. Users sign transactions in their wallet. Django stores marketplace state and verifies the submitted transaction signature against the selected Solana RPC before marking a purchase confirmed.

## Requirements

- Node.js 22+ (tested local runtime)
- npm
- Python 3.12 (tested local runtime)
- A Solana wallet extension such as Phantom
- Optional: PostgreSQL 14+

The backend falls back to SQLite for local development, so PostgreSQL is not required for the first local test.

## First-time setup

### 1. Frontend

From the project root:

```bash
npm ci
```

Create `.env.local` if you want to override the default API URL:

```env
NEXT_PUBLIC_API_URL=/api
BACKEND_ORIGIN=http://127.0.0.1:8000
```

### 2. Backend

Open a second terminal and enter the backend:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_demo
```

On Windows PowerShell the virtual environment activation command is:

```powershell
.venv\Scripts\Activate.ps1
```

Start Django:

```bash
python manage.py runserver 127.0.0.1:8000
```

Check the API:

```bash
curl http://127.0.0.1:8000/api/health/
```

You should get:

```json
{"ok":true,"service":"AdMint API"}
```

### 3. Start Next.js

Open a third terminal in the project root:

```bash
npm run dev
```

Open:

```text
http://localhost:3000
```

## Test the full marketplace flow

### Test A — create a real listing

1. Connect wallet A.
2. Select Solana Devnet.
3. Click **List a surface**.
4. Enter a price and duration.
5. Submit.
6. Refresh the browser.

The listing should still exist because it is stored in Django, not React state.

### Test B — buy the listing

Use a second wallet (wallet B) with Devnet SOL.

1. Connect wallet B.
2. Find wallet A's listing.
3. Click **Buy rights**.
4. Django first reserves the listing for five minutes.
5. The existing Solana transaction flow creates the Ad Right and sends the seller payment.
6. Confirm the transaction in Phantom.
7. The frontend waits for Solana confirmation.
8. Django verifies the transaction signature with the selected Solana RPC.
9. Django marks the listing as `sold` and creates the Ad Right record.
10. The UI shows `SOLD` and the Explorer link.

### Test C — verify persistence

Refresh the page after the purchase.

The listing should remain `SOLD` because the status is now stored by Django.

You can also inspect the API directly:

```bash
curl http://127.0.0.1:8000/api/listings/
```

And for a wallet's purchases:

```bash
curl "http://127.0.0.1:8000/api/purchases/?wallet=YOUR_WALLET_ADDRESS"
```

## Django admin

Create an admin account:

```bash
cd backend
source .venv/bin/activate
python manage.py createsuperuser
```

Then open:

```text
http://127.0.0.1:8000/admin/
```

The admin exposes listings, purchases, wallet profiles, and Ad Rights.

## PostgreSQL

For a production-like local setup, create a PostgreSQL database and set `DATABASE_URL` in `backend/.env` or the shell environment:

```env
DATABASE_URL=postgresql://admint:password@localhost:5432/admint
```

The backend automatically uses that database when `DATABASE_URL` is present. Without it, SQLite is used.

## API endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/health/` | API health check |
| GET | `/api/ready/` | Database/cache readiness; returns 503 on dependency failure |
| GET | `/api/listings/` | Marketplace listings |
| POST | `/api/listings/` | Create a listing |
| GET | `/api/listings/<id>/` | Listing details |
| POST | `/api/purchases/prepare/` | Reserve a listing and create a pending purchase |
| POST | `/api/purchases/<id>/confirm/` | Verify Solana transaction and finalize purchase |
| POST | `/api/purchases/<id>/cancel/` | Release a pending reservation |
| GET | `/api/purchases/?wallet=<address>` | Purchases for a wallet |
| GET | `/api/ad-rights/?wallet=<address>` | Ad Rights owned by a wallet |

## Important security boundary

Django does **not** receive wallet private keys or sign user transactions. The browser wallet remains responsible for signing. Django stores application state and verifies the resulting transaction signature.

Wallet-signature authentication, buyer/seller permissions, purchase-specific transaction verification and rate limits are implemented and tested. A real Devnet purchase has been verified. Public deployment and mainnet readiness are separate checks.

The prepared [production deployment](deploy/README.md) uses validated Django settings, PostgreSQL with a non-superuser application role, shared Redis rate limits, Caddy HTTPS, database/cache readiness and daily private PostgreSQL dumps. Generate the private environment once with `python deploy/configure.py YOUR_REAL_DOMAIN`. The existing local database remains a development database; migrating its data to PostgreSQL requires a staging import rehearsal. Docker container builds/runtime, backup restoration, public HTTPS and the target server configuration must still be verified on a Docker host before launch.

## Current hackathon prototype

The tested purchase demonstration uses Solana Devnet. This is not a verified Mainnet release. Purchases pay the seller directly; the app has no escrow and a refund request does not automatically move funds.

Listings open full detail pages. Sellers can attach JPG/PNG/WebP photos (up to 5 MB) at publication, and remove their own unsold listings when no purchase is active. Removal hides the listing while preserving records. Accounts, profiles, following, notifications, saved listings, private order chat, creative/proof uploads and verified reviews are included.

### Windows setup
Install Node.js 22 and Python 3.12, then run `SETUP-WINDOWS.cmd` followed by `START-WINDOWS.cmd`. The code-only repository starts with an empty local database. Optional Google OAuth requires your own private credentials; see `GOOGLE-LOGIN-SETUP.md`.

### Checks
```sh
python backend/manage.py test accounts api --noinput
npm run lint
npx tsc --noEmit
```

Deployment configuration is provided in `deploy/README.md`; a public deployment has not been verified. Local databases, sessions, private files, secrets and wallet keypairs are excluded. Fictional generated video imagery is in `qa/video-demo`; demo accounts/listings are not included in this repository.
