# src/poller.py
#
# The Search Poll worker — your ingestion source on the Free tier.
#
# What it does every POLL_INTERVAL_SECONDS:
#   1. Call GET /2/tweets/search/recent with your query
#   2. Convert each raw Twitter JSON tweet into a clean TweetEvent
#   3. Pass the event to on_event() — that's the handoff to Layer 2
#
# The since_id trick: Twitter returns only tweets newer than that ID,
# so each poll fetches only new tweets, never the same ones twice.

import asyncio
import logging
from datetime import timezone, datetime
from typing import Callable, Awaitable
import httpx

from ingestion_layer.models import TweetEvent

logger = logging.getLogger(__name__)


search_url = "https://api.twitter.com/2/tweets/search/recent"
tweet_fields = "id", "author_id", "created_at", "lang", "in_reply_to_user_id", "coversation_id"
expansions = "author_id"
user_fields = "username"

# Type alias for the handoff callback
OnEventCallback = Callable[[TweetEvent], Awaitable[None]]


class SearchPoller:
    """
    Polls Twitter's recent search endpoint on a fixed interval.
 
    Parameters
    ----------
    bearer_token : your Twitter API Bearer Token
    query        : Twitter search query (e.g. "@YourHandle -is:retweet lang:en")
    on_event     : async callback — called once per new tweet
                   THIS is the handoff point to Layer 2
    interval     : seconds between polls (Free tier minimum: 900)
    """

    def __init__(self, bearer_token:str, query:str, on_event:OnEventCallback, interval:int=900):
        self.bearer_token = bearer_token
        self._query = query
        self._on_event = on_event
        self._interval = interval
        self._since_id:str | None = None  # Track the ID of the most recent tweet we've seen
        self._running = False

        self._http = httpx.AsyncClient(
            headers={"Authorization": f"Bearer {self.bearer_token}"},
            timeout=15.0
        )

    async def start(self):
        """Run the poll loop forever."""
        self._running = True
        logger.info("poller started | query=%r | interval=%ds", self._query, self._interval)

        while self._running:
            try:
                await self._poll_once()
            except Exception as e:
                logger.error("poll error: %s", e, exc_info=True)
                await asyncio.sleep(self._interval)  # Wait before retrying on error
    async def stop(self):
        """Stop the poll loop."""
        self._running = False
        await self._http.aclose()
        logger.info("poller stopped")

    async def _poll_once(self):
        """Perform one poll: fetch new tweets and call on_event for each."""
        params = self._build_params()
        response = await self._http.get(search_url, params=params)

        if response.status_code == 429:
            reset_at = int(response.headers.get("x-rate-limit-reset", 0))
            wait = max(reset_at - int(datetime.now(timezone.utc).timestamp()), 60)
            logger.warning("rate limit hit, waiting %ds until reset", wait)
            await asyncio.sleep(wait)
            return
        
        response.raise_for_status()
        data = response.json()
        tweets = data.get("data", [])

        if not tweets:
            logger.info("no new tweets found")
            return
        
        users = {u["id"]: u["username"] for u in data.get("includes", {}).get("users", [])}

        for raw in tweets:
            event = self._parse(raw, users)
            await self._on_event(event)     # ← handoff to Layer 2

        # Update since_id to the newest tweet so next poll only fetches newer ones
        newest_id = tweets[0]["id"]
        if self._since_id is None or int(newest_id) > int(self._since_id):
            self._since_id = newest_id

        logger.info("poll complete — %d tweet(s) handed off | since_id=%s",
                    len(tweets), self._since_id)
        
    def _build_params(self) -> dict:
        """Construct the query parameters for the Twitter API request."""
        params = {
            "query": self._query,
            "tweet.fields": tweet_fields,
            "expansions": expansions,
            "user.fields": user_fields,
            "max_results": 10
        }

        if self._since_id:
            params["since_id"] = self._since_id
        return params
    
    @staticmethod
    def _parse(raw: dict, users: dict[str, str]) -> TweetEvent:
        return TweetEvent(
            tweet_id        = raw["id"],
            text            = raw["text"],
            author_id       = raw["author_id"],
            author_username = users.get(raw["author_id"], "unknown"),
            created_at      = datetime.fromisoformat(
                                  raw["created_at"].replace("Z", "+00:00")),
            source          = "poll",
            lang            = raw.get("lang", "und"),
            in_reply_to_id  = raw.get("in_reply_to_user_id"),
            conversation_id = raw.get("conversation_id"),
        )