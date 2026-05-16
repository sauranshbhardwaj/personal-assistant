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

## Expose The Webhook With ngrok

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
Set weekly goal 2000 calories 170g protein
```

## Behavior Notes

- Reminder texts are parsed by `app/parser.py` using deterministic rules.
- The parser interface is intentionally small so it can later be replaced with an OpenAI API parser.
- Confirmed reminders create reminder events for the next rolling 30 days.
- Reminder events nudge every `NUDGE_INTERVAL_MINUTES` until you reply `DONE`, `SKIP`, `SNOOZE 10`, `SNOOZE 30`, or `MAX_NUDGES` is reached.
- Done reminders use status `done`.
- Telegram transport lives in `app/telegram_client.py`.
- This local MVP does not include migrations yet. If you have an older `health_reminders.db`, delete it and restart the app so SQLite recreates the Telegram-only schema with `chat_id` columns.
