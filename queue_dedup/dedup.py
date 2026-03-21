 # Answers one question: "have we already seen this tweet ID?"
#
# Two backends with an identical interface:
#   MemoryDedup — what you're using now (resets on restart)
#   RedisDedup  — swap in when you install Redis, zero other changes
#
# The queue calls dedup.check_and_mark(tweet_id) before accepting
# any event. Returns True = duplicate, drop it. False = new, keep it.


import logging
import time
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


# How long to remember a tweet ID before expiring it.
# 48 hours covers all realistic retry windows.
SEEN_TTL_SECONDS = 48 * 60 * 60

class BaseDedup(ABC):

    @abstractmethod
    def mark_seen(self, tweet_id:str) -> None:
        ...

    def check_and_mark(self, tweet_id:str) -> bool:
        """
        Returns True  → duplicate, already seen, drop the event.
        Returns False → new tweet, mark it and let it through.
        """
        if self.is_duplicate(tweet_id):
            logger.debug("duplicate dropped: %s", tweet_id)
            return True
        self.mark_seen(tweet_id)
        return False
    
class MemoryDedup(BaseDedup):
    """
    In-memory dedup. No dependencies. Fine for local development.
    State is lost when the process restarts — swap for RedisDedup
    in production.
    Stores {tweet_id: expiry_timestamp} and evicts expired entries
    on each check so memory doesn't grow forever.
    """

    def __init__(self):
        self._seen:dict[str, float] = {}

    def _evict_expired(self) -> None :
        now = time.time()
        expired = [k for k, exp in self._seen.items() if exp < now]
        for k in expired:
            del self._seen[k]

    def is_duplicate(self, tweet_id:str) -> bool:
        self._evict_expired()
        return tweet_id in self._seen
    
    def mark_seen(self, tweet_id:str) -> None:
        self._seen[tweet_id] = time.time() + SEEN_TTL_SECONDS
        logger.debug("marked seen: %s  (cache size: %d)", tweet_id, len(self._seen))

    
class RedisDedup(BaseDedup):
    """
    Redis-backed dedup. Survives restarts. Shared across workers.
    Swap in by changing build_dedup() in main.py — nothing else changes.
 
    Requires:  pip install redis
    Each key:  bot:{bot_name}:seen:{tweet_id}  TTL = 48 h
    """
 
    def __init__(self, redis_client, bot_name: str):
        self._r      = redis_client
        self._prefix = f"bot:{bot_name}:seen"
 
    def _key(self, tweet_id: str) -> str:
        return f"{self._prefix}:{tweet_id}"
 
    def is_duplicate(self, tweet_id: str) -> bool:
        return bool(self._r.exists(self._key(tweet_id)))
 
    def mark_seen(self, tweet_id: str) -> None:
        self._r.setex(self._key(tweet_id), SEEN_TTL_SECONDS, "1")
        logger.debug("marked seen (redis): %s", tweet_id)
 


