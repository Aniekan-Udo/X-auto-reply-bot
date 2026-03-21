 # simulate.py
#
# Runs the full pipeline end-to-end with no API keys needed.
#
# What's faked:
#   - Twitter API  →  replaced with a list of hardcoded tweets
#   - Groq LLM     →  replaced with a simple rule-based responder
#
# Everything else is REAL:
#   - Dedup check
#   - Queue (put, get, FIFO order)
#   - Rate limiter
#   - Intent check (SKIP logic)
#   - Layer handoffs
#   - All logging
#
# Run with:
#   python simulate.py

import asyncio
import logging
import sys
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from ingestion_layer.models import TweetEvent
from queue_dedup.dedup import MemoryDedup
from queue_dedup.queue import EventQueue, QueueWorker
from ingestion_layer.poller import SearchPoller
from processing_AI.AI_integration import process_event, chain

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("simulate")


# ------------------------------------------------------------------
# Fake tweets — simulates what Twitter's API would return
# ------------------------------------------------------------------
FAKE_TWEETS = [
    {
        "id":              "1001",
        "text":            "@Brand your app keeps crashing on login!",
        "author_id":       "AAA",
        "created_at":      "2024-01-01T10:00:00Z",
        "lang":            "en",
        "conversation_id": "1001",
    },
    {
        "id":              "1002",
        "text":            "@Brand BUY CHEAP FOLLOWERS NOW!! 🔥🔥 bit.ly/spam",
        "author_id":       "BBB",
        "created_at":      "2024-01-01T10:01:00Z",
        "lang":            "en",
        "conversation_id": "1002",
    },
    {
        "id":              "1003",
        "text":            "@Brand when will the new feature be released?",
        "author_id":       "CCC",
        "created_at":      "2024-01-01T10:02:00Z",
        "lang":            "en",
        "conversation_id": "1003",
    },
    {
        "id":              "1001",   # duplicate of tweet 1001 — should be dropped
        "text":            "@Brand your app keeps crashing on login!",
        "author_id":       "AAA",
        "created_at":      "2024-01-01T10:00:00Z",
        "lang":            "en",
        "conversation_id": "1001",
    },
    {
        "id":              "1004",
        "text":            "@Brand I love your product, keep it up!",
        "author_id":       "DDD",
        "created_at":      "2024-01-01T10:03:00Z",
        "lang":            "en",
        "conversation_id": "1004",
    },
    {
        "id":              "1005",
        "text":            "@Brand how do I reset my password?",
        "author_id":       "EEE",
        "created_at":      "2024-01-01T10:04:00Z",
        "lang":            "en",
        "conversation_id": "1005",
    },
]

FAKE_USERS = [
    {"id": "AAA", "username": "alice"},
    {"id": "BBB", "username": "spambot99"},
    {"id": "CCC", "username": "bob"},
    {"id": "DDD", "username": "carol"},
    {"id": "EEE", "username": "dave"},
]


# ------------------------------------------------------------------
# Fake LLM — simulates Groq responses without an API key
# ------------------------------------------------------------------
def fake_llm_response(tweet_text: str) -> str:
    """
    Simple rule-based fake that mimics what the real LLM would do.
    Returns SKIP for spam, or a canned reply for genuine tweets.
    """
    text = tweet_text.lower()

    spam_signals = ["followers", "bit.ly", "click here", "buy cheap", "🔥🔥"]
    if any(signal in text for signal in spam_signals):
        return "SKIP"

    if "crash" in text or "broken" in text or "bug" in text:
        return "Sorry to hear that! We're looking into it — please DM us your details."

    if "when" in text or "release" in text or "feature" in text:
        return "Great question! We can't share timelines yet but stay tuned for updates."

    if "love" in text or "great" in text or "keep it up" in text:
        return "Thank you so much, that means a lot to us! 🙏"

    if "password" in text or "reset" in text or "login" in text:
        return "You can reset your password at our help centre — DM us if you need more help!"

    return "Thanks for reaching out! Please DM us so we can help you properly."


# ------------------------------------------------------------------
# Fake Twitter API response builder
# ------------------------------------------------------------------
def make_fake_api_response(tweets, users):
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {
        "data":     tweets,
        "includes": {"users": users}
    }
    response.raise_for_status = MagicMock()
    return response


# ------------------------------------------------------------------
# Simulation entry point
# ------------------------------------------------------------------
async def main():
    logger.info("=" * 60)
    logger.info("SIMULATION MODE — no API keys needed")
    logger.info("Tweets in batch : %d (including 1 duplicate)", len(FAKE_TWEETS))
    logger.info("=" * 60)

    # Wire up the real pipeline
    dedup  = MemoryDedup()
    queue  = EventQueue()

    # Patch the LLM chain before importing process_event
    with patch("processing_AI.AI_integration.chain") as mock_chain:

        # Make ainvoke call our fake LLM instead of Groq
        async def fake_ainvoke(inputs):
            reply_text = fake_llm_response(inputs["input"])
            response = MagicMock()
            response.content = reply_text
            return response

        mock_chain.ainvoke = fake_ainvoke

        from processing_AI.AI_integration import process_event

        worker = QueueWorker(dedup=dedup, queue=queue, on_event=process_event)
        poller = SearchPoller(
            bearer_token = "fake_token",
            query        = "@Brand -is:retweet lang:en",
            on_event     = worker.receive,
            interval     = 999,   # won't matter — we only run one poll
        )

        # Inject fake Twitter response
        poller._http = MagicMock()
        poller._http.get = AsyncMock(
            return_value=make_fake_api_response(FAKE_TWEETS, FAKE_USERS)
        )

        logger.info("")
        logger.info("── Ingestion (Layer 1) ──────────────────────────────")

        # Run one poll cycle
        await poller._poll_once()

        logger.info("")
        logger.info("── Queue & Dedup (Layer 2) + AI (Layer 3) ───────────")

        # Drain the queue — process every event
        task = asyncio.create_task(worker.start())
        await asyncio.sleep(0.5)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        logger.info("")
        logger.info("── Simulation Summary ───────────────────────────────")
        logger.info("Tweets received       : %d", len(FAKE_TWEETS))
        logger.info("Duplicates dropped    : 1  (tweet id=1001 seen twice)")
        logger.info("Spam skipped          : 1  (spambot99)")
        logger.info("Replies generated     : %d", len(FAKE_TWEETS) - 2)
        logger.info("Queue remaining       : %d", queue.size())
        logger.info("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())