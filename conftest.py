import pytest
from datetime import datetime, timezone


def make_tweet(
    tweet_id="1001",
    text="Hey @Brand your app is broken!",
    author_username="john_doe",
    source="poll",
    lang="en",
):
    from ingestion_layer.models import TweetEvent
    return TweetEvent(
        tweet_id        = tweet_id,
        text            = text,
        author_id       = "9999",
        author_username = author_username,
        created_at      = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
        source          = source,
        lang            = lang,
    )


@pytest.fixture
def tweet():
    return make_tweet()

@pytest.fixture
def spam_tweet():
    return make_tweet(tweet_id="1002", text="Buy cheap followers now!! ")

@pytest.fixture
def duplicate_tweet():
    return make_tweet(tweet_id="1001")
