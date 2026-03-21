# test_models.py

from datetime import datetime, timezone
from ingestion_layer.models import TweetEvent
from ingestion_layer.poller import SearchPoller


class TestTweetEvent:

    def test_fields_are_stored_correctly(self, tweet):
        assert tweet.tweet_id        == "1001"
        assert tweet.text            == "Hey @Brand your app is broken!"
        assert tweet.author_username == "john_doe"
        assert tweet.source          == "poll"
        assert tweet.lang            == "en"

    def test_optional_fields_default_to_none(self, tweet):
        assert tweet.in_reply_to_id  is None
        assert tweet.conversation_id is None

    def test_repr_truncates_long_text(self):
        long_text = "a" * 100
        event = TweetEvent(
            tweet_id="1", text=long_text, author_id="1",
            author_username="user",
            created_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
            source="poll"
        )
        assert "…" in repr(event)

    def test_repr_does_not_truncate_short_text(self, tweet):
        assert "…" not in repr(tweet)


class TestSearchPollerParser:

    def _raw_tweet(self):
        return {
            "id":            "1001",
            "text":          "Hey @Brand your app is broken!",
            "author_id":     "9999",
            "created_at":    "2024-01-01T12:00:00Z",
            "lang":          "en",
            "conversation_id": "1001",
        }

    def _users(self):
        return {"9999": "john_doe"}

    def test_parse_maps_all_fields(self):
        event = SearchPoller._parse(self._raw_tweet(), self._users())
        assert event.tweet_id        == "1001"
        assert event.text            == "Hey @Brand your app is broken!"
        assert event.author_id       == "9999"
        assert event.author_username == "john_doe"
        assert event.source          == "poll"
        assert event.lang            == "en"
        assert event.conversation_id == "1001"

    def test_parse_created_at_is_utc(self):
        event = SearchPoller._parse(self._raw_tweet(), self._users())
        assert event.created_at.tzinfo == timezone.utc
        assert event.created_at.year   == 2024

    def test_parse_unknown_author_falls_back(self):
        event = SearchPoller._parse(self._raw_tweet(), {})
        assert event.author_username == "unknown"

    def test_parse_missing_lang_defaults_to_und(self):
        raw = self._raw_tweet()
        del raw["lang"]
        event = SearchPoller._parse(raw, self._users())
        assert event.lang == "und"

    def test_parse_missing_conversation_id_is_none(self):
        raw = self._raw_tweet()
        del raw["conversation_id"]
        event = SearchPoller._parse(raw, self._users())
        assert event.conversation_id is None
