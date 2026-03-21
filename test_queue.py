# test_queue.py

import pytest
import asyncio
from queue_dedup.queue import EventQueue, QueueWorker
from queue_dedup.dedup import MemoryDedup
from conftest import make_tweet


@pytest.fixture
def queue():
    return EventQueue()


@pytest.fixture
def dedup():
    return MemoryDedup()


@pytest.fixture
def processed_events():
    return []


@pytest.fixture
def worker(dedup, queue, processed_events):
    async def on_event(event):
        processed_events.append(event)
    return QueueWorker(dedup=dedup, queue=queue, on_event=on_event)


class TestEventQueue:

    @pytest.mark.asyncio
    async def test_put_and_get(self, queue, tweet):
        await queue.put(tweet)
        result = await queue.get()
        assert result.tweet_id == tweet.tweet_id

    @pytest.mark.asyncio
    async def test_fifo_order(self, queue):
        tweet_a = make_tweet(tweet_id="1001")
        tweet_b = make_tweet(tweet_id="1002")
        tweet_c = make_tweet(tweet_id="1003")
        await queue.put(tweet_a)
        await queue.put(tweet_b)
        await queue.put(tweet_c)
        assert (await queue.get()).tweet_id == "1001"
        assert (await queue.get()).tweet_id == "1002"
        assert (await queue.get()).tweet_id == "1003"

    @pytest.mark.asyncio
    async def test_size_tracks_correctly(self, queue, tweet):
        assert queue.size() == 0
        await queue.put(tweet)
        assert queue.size() == 1
        await queue.get()
        assert queue.size() == 0


class TestQueueWorker:

    @pytest.mark.asyncio
    async def test_new_tweet_enters_queue(self, worker, queue, tweet):
        await worker.receive(tweet)
        assert queue.size() == 1

    @pytest.mark.asyncio
    async def test_duplicate_tweet_is_dropped(self, worker, queue, tweet):
        await worker.receive(tweet)
        await worker.receive(tweet)
        assert queue.size() == 1

    @pytest.mark.asyncio
    async def test_different_tweets_both_enter_queue(self, worker, queue):
        await worker.receive(make_tweet(tweet_id="1001"))
        await worker.receive(make_tweet(tweet_id="1002"))
        assert queue.size() == 2

    @pytest.mark.asyncio
    async def test_worker_calls_on_event(self, worker, queue, processed_events):
        await queue.put(make_tweet(tweet_id="1001"))
        task = asyncio.create_task(worker.start())
        await asyncio.sleep(0.05)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        assert len(processed_events) == 1
        assert processed_events[0].tweet_id == "1001"

    @pytest.mark.asyncio
    async def test_worker_processes_multiple_events(self, worker, queue, processed_events):
        for i in range(3):
            await queue.put(make_tweet(tweet_id=str(1001 + i)))
        task = asyncio.create_task(worker.start())
        await asyncio.sleep(0.1)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        assert len(processed_events) == 3
