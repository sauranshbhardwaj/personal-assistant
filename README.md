# Personal SMS Health Reminder Assistant

An MVP FastAPI backend for a personal SMS-based reminder assistant. It receives inbound Twilio SMS webhooks, parses plain-English reminder instructions, asks for confirmation, creates local reminder events, and sends outbound SMS reminders.

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
   export TWILIO_ACCOUNT_SID="your-account-sid"
   export TWILIO_AUTH_TOKEN="your-auth-token"
   export TWILIO_PHONE_NUMBER="+15551234567"
   export MY_PHONE_NUMBER="+15557654321"
   export DATABASE_URL="sqlite:///./health_reminders.db"
   export NUDGE_INTERVAL_MINUTES=15
   export MAX_NUDGES=4
   export DAILY_SUMMARY_HOUR=20
   export SUNDAY_GOAL_PROMPT_HOUR=18
   ```

If Twilio credentials are missing, the app records outbound messages locally and logs them instead of sending real SMS.

## Run Locally

```bash
uvicorn app.main:app --reload
```

Useful local endpoints:

- `GET /health`
- `POST /twilio/inbound`
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

Your Twilio webhook URL will be:

```text
https://abc123.ngrok-free.app/twilio/inbound
```

## Configure Twilio Inbound SMS

1. Open the Twilio Console.
2. Go to Phone Numbers, then Manage, then Active numbers.
3. Select your Twilio phone number.
4. Under Messaging, set "A message comes in" to:

   ```text
   https://abc123.ngrok-free.app/twilio/inbound
   ```

5. Use HTTP `POST`.
6. Save the phone number configuration.

TODO before exposing this beyond personal use: enable Twilio request signature verification on `/twilio/inbound`. The local MVP intentionally leaves this off for easier ngrok development.

## Example SMS Commands

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
