# main.py
#
# Wires the two layers together:
#
#   Layer 1 (Ingestion)
#     SearchPoller  →  finds tweets, calls worker.receive()
#
#   Layer 2 (Queue & Dedup)
#     QueueWorker.receive()  →  dedup check  →  EventQueue
#     QueueWorker.start()    →  drains queue  →  calls on_event()
#
#   on_event() below is the handoff to Layer 3 (AI).
#   Right now it just prints — replace its body when you build Layer 3.
#
# Run with:
#   python main.py

import asyncio
import logging
import os
import sys

from dotenv import load_dotenv

from ingestion_layer.models import TweetEvent
from queue_dedup.dedup import MemoryDedup
from queue_dedup.queue import  QueueWorker
from ingestion_layer.poller import SearchPoller
from processing_AI.AI_integration import process_event

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("main")


# ------------------------------------------------------------------
# LAYER 3 HANDOFF — replace this body when you build the AI layer
# ------------------------------------------------------------------
async def on_event(event: TweetEvent) -> None:
    """
    Called once for every tweet that passed dedup and left the queue.
    This is where Layer 2 ends and Layer 3 (AI processing) begins.

    When you build Layer 3, this becomes:
        await ai_layer.process(event)
    """
    logger.info("→ LAYER 3 HANDOFF  %r", event)


# ------------------------------------------------------------------
# Entry point
# ------------------------------------------------------------------
async def main() -> None:
    load_dotenv()

    bearer = os.getenv("TWITTER_BEARER_TOKEN", "")
    if not bearer or bearer == "your_bearer_token_here":
        logger.error(
            "TWITTER_BEARER_TOKEN is not set.\n"
            "  1. Copy .env.example to .env\n"
            "  2. Paste your Bearer Token from developer.twitter.com\n"
            "  3. Run again."
        )
        sys.exit(1)

    # Layer 2 — build dedup + queue + worker
    dedup  = MemoryDedup()
    queue  = process_event
    worker =  QueueWorker(dedup=dedup) # ← Layer 3 wired here


    # Layer 1 — poller hands every incoming tweet to worker.receive()
    poller = SearchPoller(
        bearer_token = bearer,
        query        = os.getenv("SEARCH_QUERY", "@YourHandle -is:retweet lang:en"),
        on_event     = worker.receive,   # <- Layer 1 handoff to Layer 2
        interval     = int(os.getenv("POLL_INTERVAL_SECONDS", "900")),
    )


    logger.info("starting — Layer 1 (ingestion) + Layer 2 (queue & dedup)")

    try:
        await asyncio.gather(
            poller.start(),    # Layer 1 — keeps polling Twitter
            worker.start(),    # Layer 2 — keeps draining the queue
        )
    except (KeyboardInterrupt, asyncio.CancelledError):
        logger.info("shutting down…")
        await poller.stop()


if __name__ == "__main__":
    asyncio.run(main())