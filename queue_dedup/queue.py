# queue_dedup/queue.py
import os
import logging
from celery import Celery
from ingestion_layer.models import TweetEvent
from queue_dedup.dedup import BaseDedup

logger = logging.getLogger(__name__)

app = Celery(
    "tasks",
    broker=os.environ["CELERY_BROKER_URL"],  # tells Celery to USE RabbitMQ
    backend=os.environ["CELERY_RESULT_BACKEND"]  # tells Celery to USE Redis
)


class QueueWorker:
    """
    Receives tweets from ingestion, runs dedup,
    then dispatches to Celery for AI processing.
    """

    def __init__(self, dedup: BaseDedup):
        self._dedup = dedup

    async def receive(self, event: TweetEvent):
        """
        Entry point from Layer 1.
        Checks dedup then dispatches to Celery.
        """
        if self._dedup.check_and_mark(event.tweet_id):
            logger.debug("duplicate dropped: %s", event.tweet_id)
            return

        # Dispatch to Celery — this is the Layer 2 → 3 handoff
        from processing_AI.AI_integration import process_event
        process_event.delay(event.__dict__)
        logger.info("dispatched to celery: %s", event.tweet_id)