# X (Twitter) AI Auto-Reply Bot

A bot that keeps an eye on popular trading accounts on **X (Twitter)**, writes clever, on-brand replies to their posts using AI, **checks that each reply is safe**, and only then posts it. Anything it's unsure about is sent to your phone so you can approve or reject it with one tap.

---

## What is this?

Brands grow on X by joining the conversation, replying quickly and cleverly to the big accounts in their industry. But doing that by hand all day is exhausting, and a single bad reply can embarrass the brand.

This bot does the work for you, **carefully**:

1. **It watches X** for new posts from the accounts you choose.
2. **It writes a reply** in your brand's voice: witty, knowledgeable, a little sarcastic, never rude.
3. **It checks the reply for risk** before anything is posted.
4. **Safe replies are posted automatically.**
5. **Borderline replies are sent to you on Telegram** with **Approve** and **Reject** buttons.
6. **Risky replies are thrown away**, and nothing is posted.
7. **Everything is recorded** in an Airtable spreadsheet, so you can see what the bot did and why.

There's also a **practice mode** ("dry run"), which is switched on by default. The bot does everything *except* actually post, so you can see what it *would* have said before letting it go live.

---

## How does it work? (the simple version)

Think of it as a small team where each member has one job:

```
   The Watcher          Checks X every 15 minutes for new posts
          │
          ▼
   The Filter           Ignores posts it has already seen, and drops
          │             obvious spam ("100x gem!", "DM for signals", giveaways…)
          ▼
   The Writer           AI reads the post and drafts a reply in your brand voice.
          │             It can also decide a post isn't worth replying to.
          ▼
   The Safety Checker   A second AI gives the reply a risk score from 0 to 1
          │
    ┌─────┼──────────────────────┐
    ▼     ▼                      ▼
  Safe  Borderline             Risky
 (<0.3) (0.3 – 0.7)            (>0.7)
    │     │                      │
    │     ▼                      ▼
    │   Sent to you on         Discarded
    │   Telegram: Approve / Reject
    │     │ (if approved)
    ▼     ▼
   The Publisher        Posts the reply on X and records it in Airtable
```

### What the brand voice sounds like

| Someone posts… | The bot might reply… |
|---|---|
| "This coin just pumped 50% on no news wtf" | "Classic meme coin chaos. Whale sneezed or an influencer hit post — same energy. What pumps for no reason tends to dump for even less. DYOR before chasing." |
| "The market is crashing everything is over" | "Every cycle has a graveyard of 'this is the end' tweets. Zoom out — BTC has died 400+ times according to headlines." |
| "100x gem alert DM me for signals" | *(skipped: spam)* |

### Built-in safety rules

- The bot **never gives buy or sell advice** and **never predicts prices**.
- Spam, scams, "signal" sellers and fake giveaways are **filtered out before the AI even sees them**.
- The bot **never replies to the same post twice**.
- It limits itself to **60 AI replies per hour** so it doesn't flood X or run up costs.

---

## What you need before starting

Someone comfortable with a computer terminal will need to do the setup. Here's what to have ready:

| What | Why | Where to get it (free tiers available) |
|---|---|---|
| **X (Twitter) developer account** | So the bot can read and post on X | <https://developer.x.com> |
| **Groq account** | Runs the AI that writes and checks replies | <https://console.groq.com> |
| **Telegram bot** | Sends you borderline replies to approve | Message **@BotFather** on Telegram |
| **Your Telegram chat ID** | So the bot knows where to send approvals | Message **@userinfobot** on Telegram |
| **Airtable account** | Keeps the activity log and stats | <https://airtable.com>. Create a base with two tables: **Audit Log** and **Metrics** |
| **Docker** | Runs the supporting services with one command | <https://www.docker.com/products/docker-desktop/> |

> **Tip:** An **API key / token** is like a password that lets the bot use a service on your behalf. Keep them private and never upload them to GitHub.

---

## Setting it up, step by step

### Step 1 — Download the project

```bash
git clone https://github.com/Aniekan-Udo/X-auto-reply-bot.git
cd X-auto-reply-bot
```

### Step 2 — Add your settings

Create a file called `.env` in the project folder with your keys:

```ini
# X (Twitter)
TWITTER_BEARER_TOKEN=your_bearer_token
TWITTER_API_KEY=your_api_key
TWITTER_API_SECRET=your_api_secret
TWITTER_ACCESS_TOKEN=your_access_token
TWITTER_ACCESS_TOKEN_SECRET=your_access_token_secret

# Which accounts to watch
SEARCH_QUERY=from:account1 OR from:account2 -is:retweet lang:en
POLL_INTERVAL_SECONDS=900

# AI
GROQ_API_KEY=your_groq_key

# Telegram approvals
TELEGRAM_TOKEN=your_telegram_bot_token

# Activity log
AIRTABLE_API_KEY=your_airtable_token
AIRTABLE_BASE_ID=appXXXXXXXXXXXXXX

# Database and message queue
DB_PASSWORD=choose_a_password
CELERY_BROKER_URL=amqp://guest:guest@localhost:5672//
CELERY_RESULT_BACKEND=redis://localhost:6379/0

# Practice mode: true = don't actually post (recommended to start)
DRY_RUN=true
```

**Choosing who to watch:** change `SEARCH_QUERY`. For example, `from:elonmusk OR from:saylor -is:retweet lang:en` watches those two accounts, skips retweets, and only looks at English posts.

### Step 3 — Start the supporting services

```bash
docker compose up -d postgres rabbitmq redis
```

This starts the database (stores posts waiting for your approval), the message queue (passes work between the bot's "team members"), and a small cache.

### Step 4 — Install and run the bot

```bash
pip install uv          # a fast Python package installer
uv sync                 # installs everything the bot needs
```

Then run each of these in its **own terminal window**:

```bash
# 1. The Watcher: checks X for new posts
uv run python -m ingestion_layer.main

# 2. The Writer, Safety Checker and Publisher
uv run celery -A processing_AI.AI_integration worker --loglevel=info -I safety_compliance.moderator,dispatch_observability.write_tweet

# 3. The dashboard and Telegram button handler
uv run uvicorn dispatch_observability.app:app --port 8000
```

### Step 5 — Watch it in practice mode

With `DRY_RUN=true`, the worker window shows lines like:

```
DRY RUN — would have posted | tweet_id=... | reply='...'
```

Read through them. When you're happy with the replies, set `DRY_RUN=false` in `.env` and restart to go live.

### Want to try it with no accounts at all?

`simulate.py` runs the whole pipeline with **fake posts and a fake AI**, so no keys are needed. It's a quick way to see how the pieces fit together:

```bash
uv run python simulate.py
```

---

## Checking what the bot has been doing

- **Airtable:** every action (posted, practice run, rejected, sent for review) is added to your **Audit Log** table with the time and risk score. The **Metrics** table keeps running totals.
- **Dashboard links** (while the dashboard is running):

| Link | Shows |
|---|---|
| <http://localhost:8000/metrics> | Totals: replies posted, rejected, sent for review, and the success rate |
| <http://localhost:8000/metrics/audit> | The most recent 50 actions |
| <http://localhost:8000/health> | Whether the dashboard is running |

---

## Approving replies from your phone

When a reply scores between 0.3 and 0.7 on the risk scale:

1. You get a **Telegram message** with the proposed reply and two buttons: **Approve** and **Reject**.
2. **Approve** → it's posted on X straight away. **Reject** → it's dropped and logged.

For the buttons to work, Telegram must be able to reach the dashboard (step 4, window 3). Set the Telegram bot's webhook to `https://<your-public-address>/telegram/callback`. Tools like [ngrok](https://ngrok.com) can give your computer a temporary public address.

---

## Current status & limitations

This is a **portfolio project** that shows a production-style design. Some parts are still being connected:

- **Telegram chat ID:** for now, replace `YOUR_CHAT_ID` in `safety_compliance/moderator.py` with your own chat ID. It will move into the `.env` settings.
- **One-command Docker start:** the `docker-compose.yml` bot services are still being finished. Use the step-by-step commands above in the meantime.
- **X free tier:** it can only check for new posts every 15 minutes and has monthly limits. Busy accounts need a paid X API plan.
- **Memory of seen posts resets on restart.** A Redis-based version that survives restarts (`RedisDedup`) is already written and just needs switching on.
- **Airtable stats** are fine for low to medium volume but aren't designed for very high traffic.

---

## For developers

<details>
<summary>Click to expand technical details</summary>

### Tech stack

| Technology | Role |
|---|---|
| Python 3.12 (asyncio) | Core language |
| httpx | Async X API v2 client (recent search polling with `since_id`) |
| Celery + RabbitMQ | Task queue between layers; Redis as result backend |
| Groq (`llama-3.3-70b-versatile`) + LangChain | Reply generation and risk scoring |
| tenacity, limits | Retries with exponential backoff; 60/hour rate limit |
| PostgreSQL + SQLAlchemy | Human-review (HITL) job storage |
| Tweepy | Posting replies |
| Airtable (pyairtable) | Audit log and metrics |
| FastAPI | Telegram callback + metrics endpoints |
| pytest | Unit tests |

### The five layers

| Layer | Folder / file | Responsibility |
|---|---|---|
| 1. Ingestion | `ingestion_layer/poller.py`, `models.py`, `main.py` | Poll X recent search, normalise to `TweetEvent`, handle 429 rate limits |
| 2. Queue & dedup | `queue_dedup/dedup.py`, `queue.py` | 48-hour dedup (`MemoryDedup` / `RedisDedup`), dispatch to Celery |
| 3. AI processing | `processing_AI/AI_integration.py` | Spam pre-filter, brand-voice prompt, `SKIP` handling |
| 4. Safety | `safety_compliance/moderator.py` | LLM risk score → auto-approve / Telegram HITL / reject |
| 5. Dispatch & observability | `dispatch_observability/write_tweet.py`, `app.py` | Post (or dry-run) to X, Airtable audit + metrics, FastAPI endpoints |
| Database | `database/db.py` | `twitter_jobs` table and access helpers |

### Tests

```bash
uv run pytest -v
```

Tests (`test_dedup.py`, `test_models.py`, `test_poller.py`, `test_queue.py`, `test_layer3.py`) use mocks, so no real API calls are made.

### Environment variables

| Variable | Required | Description |
|---|---|---|
| `TWITTER_BEARER_TOKEN` | Yes | X API v2 bearer token (reading) |
| `TWITTER_API_KEY`, `TWITTER_API_SECRET`, `TWITTER_ACCESS_TOKEN`, `TWITTER_ACCESS_TOKEN_SECRET` | Yes, to post | X credentials for posting |
| `GROQ_API_KEY` | Yes | Groq API key |
| `TELEGRAM_TOKEN` | Yes | Telegram bot token |
| `AIRTABLE_API_KEY`, `AIRTABLE_BASE_ID` | Yes | Airtable access |
| `DB_PASSWORD` | Yes | Postgres password |
| `CELERY_BROKER_URL` | Yes | RabbitMQ URL |
| `CELERY_RESULT_BACKEND` | Yes | Redis URL |
| `SEARCH_QUERY` | — | X search query (accounts to watch) |
| `POLL_INTERVAL_SECONDS` | — | Default `900` (15 min; free-tier minimum) |
| `DRY_RUN` | — | Default `true`; set to `false` to post for real |

</details>
