 # src/models.py
#
# The normalised shape every tweet becomes after ingestion.
# Raw Twitter API JSON is messy — this dataclass is the clean
# contract between the ingestion layer and everything after it.

from dataclasses import dataclass
from datetime import datetime


@dataclass
class TweetEvent:
    tweet_id:        str          # Twitter's unique ID
    text:            str          # Full tweet text
    author_id:       str          # Twitter numeric user ID
    author_username: str          # Handle without the @
    created_at:      datetime     # Published time (UTC)
    source:          str          # "poll" | "stream" | "webhook"
    lang:            str = "und"  # Language code ("en", "fr", … "und" = unknown)
    in_reply_to_id:  str | None = None  # Parent tweet ID if this is a reply
    conversation_id: str | None = None  # Root tweet ID of the thread

    def __repr__(self) -> str:
        ts = self.created_at.strftime("%H:%M:%S")
        snippet = self.text[:60] + ("…" if len(self.text) > 60 else "")
        return f"[{ts}] @{self.author_username}: {snippet}  (id={self.tweet_id})"