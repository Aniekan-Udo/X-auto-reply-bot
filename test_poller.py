# test_poller.py

import pytest
from unittest.mock import AsyncMock, MagicMock
from ingestion_layer.poller import SearchPoller


def make_twitter_response(tweets=None, users=None, status_code=200):
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = {
        "data":     tweets or [],
        "includes": {"users": users or []}
    }
    response.raise_for_status = MagicMock()
    return response


RAW_TWEETS = [{
    "id":              "1001",
    "text":            "Hey @Brand your app is broken!",
    "author_id":       "9999",
    "created_at":      "2024-01-01T12:00:00Z",
    "lang":            "en",
    "conversation_id": "1001",
}]

RAW_USERS = [{"id": "9999", "username": "john_doe"}]


@pytest.fixture
def collected_events():
    return []


@pytest.fixture
def poller(collected_events):
    async def on_event(event):
        collected_events.append(event)
    return SearchPoller(
        bearer_token = "fake_token",
        query        = "@Brand -is:retweet",
        on_event     = on_event,
        interval     = 900,
    )


class TestSearchPoller:

    @pytest.mark.asyncio
    async def test_hands_off_new_tweets(self, poller, collected_events):
        poller._http.get = AsyncMock(
            return_value=make_twitter_response(RAW_TWEETS, RAW_USERS)
        )
        await poller._poll_once()
        assert len(collected_events) == 1
        assert collected_events[0].tweet_id == "1001"

    @pytest.mark.asyncio
    async def test_empty_response_hands_off_nothing(self, poller, collected_events):
        poller._http.get = AsyncMock(
            return_value=make_twitter_response(tweets=[], users=[])
        )
        await poller._poll_once()
        assert len(collected_events) == 0

    @pytest.mark.asyncio
    async def test_since_id_updates_after_poll(self, poller):
        poller._http.get = AsyncMock(
            return_value=make_twitter_response(RAW_TWEETS, RAW_USERS)
        )
        assert poller._since_id is None
        await poller._poll_once()
        assert poller._since_id == "1001"

    @pytest.mark.asyncio
    async def test_since_id_sent_on_second_poll(self, poller):
        poller._since_id = "1001"
        poller._http.get = AsyncMock(
            return_value=make_twitter_response(tweets=[], users=[])
        )
        await poller._poll_once()
        params = poller._http.get.call_args[1]["params"]
        assert params["since_id"] == "1001"

    @pytest.mark.asyncio
    async def test_rate_limit_does_not_crash(self, poller, collected_events):
        rate_limit_response = MagicMock()
        rate_limit_response.status_code = 429
        rate_limit_response.headers = {"x-rate-limit-reset": "0"}
        poller._http.get = AsyncMock(return_value=rate_limit_response)
        await poller._poll_once()
        assert len(collected_events) == 0
