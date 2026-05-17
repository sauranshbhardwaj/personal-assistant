# Personal Telegram Health Reminder Assistant

An MVP FastAPI backend for a personal Telegram-based reminder assistant. It receives Telegram Bot API webhook updates, parses plain-English reminder instructions, asks for confirmation, creates local reminder events, and sends reminder messages back to your configured Telegram chat.

This is a reminder-only system. It does not provide medical advice, dosage guidance, diagnosis, or medication safety recommendations. It only reminds and tracks information you explicitly enter.

## Setup

1. Create and activate a virtual environment:

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

2. Install dependencies:

   ```bash
   pip install -r requirements.txt
   pip install ".[dev]"
   ```

3. Configure environment variables:

   ```bash
   export TELEGRAM_BOT_TOKEN="1234567890:your_bot_token_from_botfather"
   export TELEGRAM_CHAT_ID="123456789"
   export DATABASE_URL="sqlite:///./health_reminders.db"
   export NUDGE_INTERVAL_MINUTES=15
   export MAX_NUDGES=4
   export DAILY_SUMMARY_HOUR=20
   export SUNDAY_GOAL_PROMPT_HOUR=18
   ```

If `TELEGRAM_BOT_TOKEN` or `TELEGRAM_CHAT_ID` is missing, the app records outbound messages locally and logs them instead of sending real Telegram messages.

## Create A Telegram Bot

1. Open Telegram and search for `@BotFather`.
2. Send:

   ```text
   /newbot
   ```

3. Follow BotFather's prompts for bot name and username.
4. Copy the bot token BotFather returns. Use it as `TELEGRAM_BOT_TOKEN`.
5. Open your new bot in Telegram and send it any message, such as:

   ```text
   hello
   ```

## Get Your TELEGRAM_CHAT_ID

Before setting a webhook, ask Telegram for recent bot updates:

```bash
curl "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/getUpdates"
```

Look for:

```json
"chat":{"id":123456789}
```

Use that value as:

```bash
export TELEGRAM_CHAT_ID="123456789"
```

If `getUpdates` returns no messages, send your bot another Telegram message and run the curl command again.

## Run Locally

```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Useful local endpoints:

- `GET /health`
- `POST /telegram/webhook`
- `POST /telegram/set-webhook`
- `POST /dev/send-test-reminder`
- `GET /dev/today`

Run tests:

```bash
pytest
```

## Optional Local Webhook Testing With ngrok

ngrok is only for local development. Railway production does not use ngrok.

With the local server running on port 8000:

```bash
ngrok http 8000
```

Copy the HTTPS forwarding URL, for example:

```text
https://abc123.ngrok-free.app
```

Your Telegram webhook URL will be:

```text
https://abc123.ngrok-free.app/telegram/webhook
```

## Set The Telegram Webhook

Option A: call Telegram directly:

```bash
curl -X POST "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/setWebhook" \
  -H "Content-Type: application/json" \
  -d '{"url":"https://abc123.ngrok-free.app/telegram/webhook"}'
```

Option B: use the local dev endpoint:

```bash
curl -X POST "http://127.0.0.1:8000/telegram/set-webhook" \
  -H "Content-Type: application/json" \
  -d '{"url":"https://abc123.ngrok-free.app/telegram/webhook"}'
```

Each time your ngrok URL changes, set the Telegram webhook again.

## Example Telegram Commands

Create reminders:

```text
Take Vitamin D 2000 IU every morning at 9 AM for 60 days
Remind me to take magnesium 400mg every night at 10 PM
Take antibiotic twice daily at 9 AM and 9 PM for 7 days
```

Confirmation and reminder actions:

```text
YES
CANCEL
DONE
SKIP
SNOOZE 10
SNOOZE 30
today
summary
help
```

Diet MVP:

```text
Log meal 650 calories 45g protein
Log lunch 650 calories 45g protein
Lunch: 650 calories, 45g protein
Log breakfast 500 calories 35g protein
Log snack 250 calories 20g protein
Log dinner 700 calories 50g protein
Set weekly goal 2000 calories 170g protein
```

The everyday meal types are `breakfast`, `lunch`, `snack`, and `dinner`. Generic `Log meal ...` still works for quick logging, but only `lunch` triggers the Omega 3 reminder.

## Seed Your Predecided Reminders

After `TELEGRAM_CHAT_ID` is configured, load the predecided active reminders with:

```bash
python -m app.seed_reminders
```

The seed is idempotent, so rerunning it updates the same reminder records and does not duplicate reminder events. It creates active reminders for Halovate Cream, Momrazone Cream, Adhydra Lotion, Uprise D3 Tablet, Creatine, Whey Protein, and Omega 3 Tablet. Uprise D3 is seeded for Sundays at `09:00` because the source reminder did not include an exact time.

Omega 3 Tablet is stored as an active reminder without fixed-time events. It triggers only once per day when you log lunch macros, for example:

```text
Log lunch 650 calories 45g protein
Lunch: 650 calories, 45g protein
```

Breakfast, dinner, snack, and generic meal logs do not trigger the Omega 3 reminder.

## Railway Production Deployment

Railway production should run one FastAPI service connected to one Railway Postgres database. Keep the service at one replica/instance for this MVP; multiple replicas would each run APScheduler and could send duplicate reminders.

Railway config lives in `railway.json`. The production start command is:

```bash
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

Railway can use `/health` as the service health check:

```bash
curl https://YOUR_RAILWAY_PUBLIC_URL/health
```

### Railway Environment Variables

Add these variables to the FastAPI app service, not only to the Postgres service. Railway provides `PORT` automatically, so do not add `PORT` manually.

Required FastAPI service variables:

```text
TELEGRAM_BOT_TOKEN=<YOUR_TELEGRAM_BOT_TOKEN_FROM_BOTFATHER>
TELEGRAM_CHAT_ID=<YOUR_NUMERIC_TELEGRAM_CHAT_ID>
DATABASE_URL=${{Postgres.DATABASE_URL}}
```

- `TELEGRAM_BOT_TOKEN` comes from BotFather after you create the bot.
- `TELEGRAM_CHAT_ID` is the numeric chat id you used during local Telegram testing.
- `DATABASE_URL` should use Railway reference variable syntax so the FastAPI service reads the Postgres connection string from the database service. If your Railway database service is named `PostgreSQL`, use `DATABASE_URL=${{PostgreSQL.DATABASE_URL}}` instead.

Optional/defaulted FastAPI service variables:

```text
NUDGE_INTERVAL_MINUTES=15
MAX_NUDGES=4
DAILY_SUMMARY_HOUR=20
SUNDAY_GOAL_PROMPT_HOUR=18
```

- `NUDGE_INTERVAL_MINUTES` controls how often sent reminders nudge before completion or skip.
- `MAX_NUDGES` controls how many nudges are sent before an event becomes missed.
- `DAILY_SUMMARY_HOUR` controls the daily summary send hour in the app timezone.
- `SUNDAY_GOAL_PROMPT_HOUR` controls the Sunday weekly-goal prompt hour in the app timezone.
- `TIMEZONE` is available for advanced use and defaults to `America/New_York`; you do not need to set it for the normal setup.

### What The Code Already Handles

- FastAPI starts from `app.main:app`.
- Railway installs production dependencies from `requirements.txt`; `pyproject.toml` also lists the same runtime dependencies.
- `DATABASE_URL` controls the database connection.
- SQLite remains the local fallback when `DATABASE_URL` is not set.
- Railway-style `postgres://...` database URLs are normalized to `postgresql://...` for SQLAlchemy.
- Tables are created on startup when they do not exist.
- APScheduler starts with the FastAPI app and shuts down when the app stops.
- `POST /telegram/webhook` receives Telegram updates.
- `POST /telegram/set-webhook` can set the Telegram webhook.
- The Telegram sender sends real messages when `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` are configured, otherwise it logs locally.
- `python -m app.seed_reminders` seeds the May 18, 2026 reminders idempotently without duplicating reminders or events.

### Manual Railway/Telegram Steps I Must Do

1. Push the latest repo to GitHub:

   ```bash
   cd /Users/sauranshbhardwaj/Documents/personal-assistant
   git add README.md app pyproject.toml requirements.txt railway.json tests
   git commit -m "Prepare Telegram reminder bot for Railway"
   git push origin main
   ```

2. In Railway, create a new project.
3. Choose **Deploy from GitHub repo** and select this repository.
4. Add a Railway Postgres database to the project.
5. Connect or copy the Railway Postgres `DATABASE_URL` into the FastAPI service variables.
6. Add these FastAPI service variables:

   ```text
   TELEGRAM_BOT_TOKEN=<YOUR_TELEGRAM_BOT_TOKEN>
   TELEGRAM_CHAT_ID=<YOUR_TELEGRAM_CHAT_ID>
   DATABASE_URL=${{Postgres.DATABASE_URL}}
   NUDGE_INTERVAL_MINUTES=15
   MAX_NUDGES=4
   DAILY_SUMMARY_HOUR=20
   SUNDAY_GOAL_PROMPT_HOUR=18
   ```

   If your Railway database service is named `PostgreSQL`, use `DATABASE_URL=${{PostgreSQL.DATABASE_URL}}` instead.

7. Confirm Railway is using this start command if it does not pick up `railway.json`:

   ```bash
   uvicorn app.main:app --host 0.0.0.0 --port $PORT
   ```

8. Keep the service at one replica/instance.
9. Generate a public Railway domain for the FastAPI service.
10. Check the deployed health endpoint:

    ```bash
    curl https://YOUR_RAILWAY_PUBLIC_URL/health
    ```

11. Set the production Telegram webhook to:

    ```text
    https://YOUR_RAILWAY_PUBLIC_URL/telegram/webhook
    ```

    Option A, direct Telegram Bot API:

    ```bash
    curl "https://api.telegram.org/bot<TELEGRAM_BOT_TOKEN>/setWebhook?url=https://YOUR_RAILWAY_PUBLIC_URL/telegram/webhook"
    ```

    Option B, app endpoint:

    ```bash
    curl -X POST "https://YOUR_RAILWAY_PUBLIC_URL/telegram/set-webhook" \
      -H "Content-Type: application/json" \
      -d '{"url":"https://YOUR_RAILWAY_PUBLIC_URL/telegram/webhook"}'
    ```

12. Run the production seed script. Prefer a Railway shell or one-off command in the FastAPI service:

    ```bash
    python -m app.seed_reminders
    ```

    If running the seed locally against production Postgres, export production env vars first:

    ```bash
    export TELEGRAM_BOT_TOKEN="<YOUR_TELEGRAM_BOT_TOKEN>"
    export TELEGRAM_CHAT_ID="<YOUR_TELEGRAM_CHAT_ID>"
    export DATABASE_URL="<RAILWAY_POSTGRES_DATABASE_URL>"
    export NUDGE_INTERVAL_MINUTES=15
    export MAX_NUDGES=4
    export DAILY_SUMMARY_HOUR=20
    export SUNDAY_GOAL_PROMPT_HOUR=18
    python -m app.seed_reminders
    ```

13. Test the deployed bot from Telegram:

    ```text
    help
    today
    Log lunch 650 calories 45g protein
    DONE
    summary
    ```

## Behavior Notes

- Reminder texts are parsed by `app/parser.py` using deterministic rules.
- The parser interface is intentionally small so it can later be replaced with an OpenAI API parser.
- Confirmed reminders create reminder events for the next rolling 30 days.
- Reminder events nudge every `NUDGE_INTERVAL_MINUTES` until you reply `DONE`, `SKIP`, `SNOOZE 10`, `SNOOZE 30`, or `MAX_NUDGES` is reached.
- Done reminders use status `done`.
- Telegram transport lives in `app/telegram_client.py`.
- Production persistence uses Railway Postgres through `DATABASE_URL`; Alembic is intentionally not required for this personal MVP.
- This local MVP does not include full migrations yet. If you see a schema error with an older `health_reminders.db`, stop the app, delete `health_reminders.db`, and restart so SQLite recreates the current Telegram-only schema with `chat_id` and meal type columns.
