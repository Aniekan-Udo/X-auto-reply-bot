from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
import os
from dotenv import load_dotenv

from tenacity import retry, stop_after_attempt, wait_exponential

import asyncio
import logging

from limits import parse
from limits.storage import MemoryStorage
from limits.strategies import FixedWindowRateLimiter

from database.db import AccessDB

save_to_db = AccessDB.save_to_db()
load_from_db = AccessDB.load_from_db()


import httpx




logger = logging.getLogger(__name__)

# Setup
storage = MemoryStorage()
rate_limiter = FixedWindowRateLimiter(storage)
limit = parse("60 per hour")


load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
groq_api_key=os.getenv("GROQ_API_KEY")


from celery import Celery
app = Celery(
    "tasks",
    broker=os.environ["CELERY_BROKER_URL"],  # tells Celery to USE RabbitMQ
    backend=os.environ["CELERY_RESULT_BACKEND"]  # tells Celery to USE Redis
)

llm = ChatGroq(model="llama-3.3-70b-versatile", groq_api_key=groq_api_key)

moderation_prompt = ChatPromptTemplate.from_messages([
    ("system", """You are a content moderator for a trading platform.
     Score the following reply on a scale of 0.0 to 1.0 for risk:
- 0.0 = completely safe, professional, no issues
- 0.5 = borderline — could be misinterpreted or slightly risky  
- 1.0 = dangerous — contains financial advice, toxic content, PII, or legal risk


Respond with ONLY a float number between 0.0 and 1.0. Nothing else.
"""), ("user", "{reply}")]
)


chain = moderation_prompt | llm

# safety_compliance/safety.py
@app.task(bind=True, max_retries=3, default_retry_delay=5)
def moderate(self,tweet_id: str, reply: str) -> str | None:
    try:
        score = asyncio.run(get_moderation_score(reply))

        if score < 0.3:
            # auto approve — pass to Layer 5
            from dispatch_observability.write_tweet import dispatch_reply
            dispatch_reply.delay(tweet_id, reply, score)  
            logger.info("approved: %s (score=%.2f)", tweet_id, score)
            return None

        elif score < 0.7:
            # grey zone — send to HITL queue
            logger.info("HITL triggered: %s (score=%.2f)", tweet_id, score)
            add_to_hitl_queue.delay(tweet_id, reply, score)
            return None

        else:
            # auto reject — drop it
            logger.info("rejected: %s (score=%.2f)", tweet_id, score)
            return None
    except Exception as e:
        logger.error("Failed to moderate tweet %s: %s", tweet_id, str(e), exc_info=True)
        raise self.retry(exc=e)  # Retry the task
    


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
async def get_moderation_score(reply: str) -> float:
    try:
        response = await chain.ainvoke({"reply":reply})
        return float(response.content.strip())
    except Exception as e:
        logger.error(f"Error occurred while fetching moderation score: {e}")
        raise


class HITLModerator:
    """
    Human-in-the-loop moderator for AI-generated replies.
    If the moderation score exceeds a certain threshold, the reply is flagged for review instead of being posted.
    """

    def __init__(self, tweet_id:int, reply:str, score:float=0.1):
        self.tweet_id = tweet_id
        self.reply = reply
        self.score = score
        self.job_id = None

    async def workflow(self):
        self.job_id = save_to_db(self.tweet_id, self.reply, self.score)  # Save the reply and score to the database for review
        try:
            await notify_via_telegram(self.job_id, self.reply)  # Notify human moderators to review this reply via email/slack/dashboard/etc.
            return self.job_id
        except Exception as e:
            logger.error(f"Error occurred while notifying via Telegram: {e}", exc_info=True)
            raise

    @staticmethod
    async def resume(job_id:str, approved:bool):
        from dispatch_observability.write_tweet import dispatch_reply
        job = load_from_db(job_id)
        if approved:
            # Layer 5 — post the reply to Twitter   
            dispatch_reply.delay(job['tweet_id'], job['reply'], job['score'])  # Post the approved reply to Twitter
        else:
            logger.info(f"Reply for tweet {job['tweet_id']} was rejected by human moderators.")


@app.task(bind=True, max_retries=3)
def add_to_hitl_queue(self, tweet_id: str, reply: str, score: float) -> str:
    try:
        job_id = asyncio.run(HITLModerator(tweet_id, reply, score).workflow())
        return job_id
    except Exception as exc:
        raise self.retry(exc=exc, countdown=2 ** self.request.retries)




async def notify_via_telegram(job_id: str, reply: str):
    """Sends a notification to human moderators via Telegram with the reply that needs review.
    The message includes inline buttons for "Approve" and "Reject" that moderators can click to approve or reject the reply."""
    
    async with httpx.AsyncClient() as client:# Use context manager to ensure proper cleanup of resources(open and close connections)
        await client.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={
                "chat_id": "YOUR_CHAT_ID",
                "text": f"Review this reply:\n\n{reply}",
            "reply_markup": {
                "inline_keyboard": [[
                    {"text": "✅ Approve", "callback_data": f"approve:{job_id}"},
                    {"text": "❌ Reject", "callback_data": f"reject:{job_id}"}
                ]]
            }
        }
    )





# A FastAPI endpoint that receives Telegram callbacks
# @app.post("/telegram/callback")
# async def telegram_callback(update: dict):
#     callback = update["callback_query"]
#     data = callback["data"]  # "approve:job_id" or "reject:job_id"
#     action, job_id = data.split(":")
#     approved = action == "approve"
#     await HITLModerator.resume(job_id, approved)
#     return {"ok": True}