# test_layer3.py

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from conftest import make_tweet


def mock_llm_response(text: str):
    response = MagicMock()
    response.content = text
    return response


class TestProcessEvent:

    @pytest.mark.asyncio
    async def test_genuine_tweet_returns_reply(self):
        tweet = make_tweet(text="Your app keeps crashing!")
        with patch("processing_AI.AI_integration.chain") as mock_chain:
            mock_chain.ainvoke = AsyncMock(
                return_value=mock_llm_response("Sorry to hear that! We're looking into it — please DM us.")
            )
            from processing_AI.AI_integration import process_event
            result = await process_event(tweet)
        assert result == "Sorry to hear that! We're looking into it — please DM us."

    @pytest.mark.asyncio
    async def test_spam_tweet_returns_none(self):
        tweet = make_tweet(text="Buy cheap followers now!! 🔥")
        with patch("processing_AI.AI_integration.chain") as mock_chain:
            mock_chain.ainvoke = AsyncMock(
                return_value=mock_llm_response("SKIP")
            )
            from processing_AI.AI_integration import process_event
            result = await process_event(tweet)
        assert result is None

    @pytest.mark.asyncio
    async def test_reply_is_stripped_of_whitespace(self):
        tweet = make_tweet(text="Where is my order?")
        with patch("processing_AI.AI_integration.chain") as mock_chain:
            mock_chain.ainvoke = AsyncMock(
                return_value=mock_llm_response("  We're checking on that for you!  \n")
            )
            from processing_AI.AI_integration import process_event
            result = await process_event(tweet)
        assert result == "We're checking on that for you!"

    @pytest.mark.asyncio
    async def test_rate_limit_returns_none(self):
        tweet = make_tweet()
        with patch("processing_AI.AI_integration.storage") as mock_storage:
            mock_storage.hit.return_value = False
            with patch("processing_AI.AI_integration.chain") as mock_chain:
                mock_chain.ainvoke = AsyncMock()
                from processing_AI.AI_integration import process_event
                result = await process_event(tweet)
            mock_chain.ainvoke.assert_not_called()
        assert result is None

    @pytest.mark.asyncio
    async def test_skip_is_case_sensitive(self):
        tweet = make_tweet(text="Should I skip the update?")
        with patch("processing_AI.AI_integration.chain") as mock_chain:
            mock_chain.ainvoke = AsyncMock(
                return_value=mock_llm_response("You can skip it for now if you prefer.")
            )
            from processing_AI.AI_integration import process_event
            result = await process_event(tweet)
        assert result is not None
        assert "skip" in result.lower()
