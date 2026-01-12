<<<<<<< HEAD
# superparser
=======
# Price Comparison Site

Web app to compare prices of products across your store and other stores, with twice-daily checks and Telegram notifications on changes.

## Quick start

1. Create and fill environment variables:

```
cp .env.example .env
```

2. Install dependencies (Python 3.10+ recommended):

```
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

3. Run the app:

```
uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000 in your browser.

## Features (planned)

- Manage stores (your store + competitors) and product links
- Parse prices using per-store CSS selectors or custom adapters
- Store price snapshots; render comparison table (stores as columns, products as rows)
- Scheduler runs twice daily to refresh prices
- Telegram bot notifies on price changes

## Configuration

See `.env.example` for config like default timezone, Telegram bot token, chat id, etc.

### Environment

- APP_TIMEZONE: e.g. `Europe/Moscow`
- DATABASE_URL: default SQLite file `sqlite:///./price_comparator.db`
- SCHEDULE_CRON_1, SCHEDULE_CRON_2: cron strings for two daily runs
- TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID: for notifications
- TELEGRAM_BOT_USERNAME: your bot username (without @)
- TELEGRAM_WEBHOOK_SECRET: random string to protect webhook
- PUBLIC_BASE_URL: public URL where this app is accessible (for Telegram webhook)
- PRIMARY_STORE_SLUG, PRIMARY_STORE_BASE_URL: your store identifier

### Usage

- Add stores at `/stores/view` (set CSS selector for price if known)
- Add products at `/products` with group key (same product across stores)
- Open `/compare` to view table and press “Обновить цены сейчас” for manual refresh

Scheduler runs on startup using the timezone. Price parsing is best-effort and may need CSS selectors per store for reliability.

## Authentication and multi-tenant

- Signup at `/auth/signup`, then login at `/auth/login`.
- Each user sees only their own stores/products and comparison table.
- To receive Telegram updates per user, open `/settings` and use the generated bot link (deep-link). The webhook endpoint `/telegram/webhook` must be accessible publicly.

>>>>>>> 5c0c798 (Initial commit: Price comparator application with stores, products, comparison, and Telegram integration)
