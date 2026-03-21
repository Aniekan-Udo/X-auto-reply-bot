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

from database.db import save_to_db, load_from_db

import httpx




logger = logging.getLogger(__name__)

# Setup
storage = MemoryStorage()
rate_limiter = FixedWindowRateLimiter(storage)
limit = parse("60 per hour")
from celery import Celery
app = Celery('tasks', broker='redis://localhost:6379/0')

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
groq_api_key=os.getenv("GROQ_API_KEY")


from celery import Celery
app = Celery('tasks', broker='redis://localhost:6379/0')

llm = ChatGroq(model="llama-3.3-70b-versatile", groq_api_key=groq_api_key)

moderation_prompt = ChatPromptTemplate.from_messages([
    ("system", """You are a content moderator for a trading platform.
     Score the following reply on a scale of 0.0 to 1.0 for risk:
- 0.0 = completely safe, professional, no issues
- 0.5 = borderline — could be misinterpreted or slightly risky  
- 1.0 = dangerous — contains financial advice, toxic content, PII, or legal risk

Reply to score: "{reply}"

Respond with ONLY a float number between 0.0 and 1.0. Nothing else.
""")]
)


chain = moderation_prompt | llm

# safety_compliance/safety.py

async def moderate(tweet_id: str, reply: str) -> str | None:
    score = await get_moderation_score(reply)

    if score < 0.3:
        # auto approve — pass to Layer 5
        logger.info("approved: %s (score=%.2f)", tweet_id, score)
        return reply

    elif score < 0.7:
        # grey zone — send to HITL queue
        logger.info("HITL triggered: %s (score=%.2f)", tweet_id, score)
        await add_to_hitl_queue(tweet_id, reply, score)
        return None

    else:
        # auto reject — drop it
        logger.info("rejected: %s (score=%.2f)", tweet_id, score)
        return None



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
        await notify_via_telegram(self.job_id, self.reply)  # Notify human moderators to review this reply via email/slack/dashboard/etc.

        return self.job_id
    
    # Later, when human responds via your UI/API (Layer 5):
    async def resume(self,job_id, approved):
        job = load_from_db(job_id)
        if approved:
            await post_reply(job['tweet_id'], job['draft'])  # Post the approved reply to Twitter
        else:
            logger.info(f"Reply for tweet {job['tweet_id']} was rejected by human moderators.")


@app.task(bind=True, max_retries=3)
async def add_to_hitl_queue(tweet_id: str, reply: str, score: float) -> str:
    asyncio.run(HITLModerator(tweet_id, reply, score).workflow())


async def post_reply(tweet_id: int, reply: str):
    # Placeholder function to post the reply to Twitter
    # In a real implementation, this would involve calling the Twitter API to post the reply
    logger.info(f"Posting reply to tweet {tweet_id}: {reply}")


async def notify_via_telegram(job_id: str, draft: str):
    async with httpx.AsyncClient() as client:# Use context manager to ensure proper cleanup of resources(open and close connections)
        await client.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={
                "chat_id": "YOUR_CHAT_ID",
                "text": f"Review this draft:\n\n{draft}",
            "reply_markup": {
                "inline_keyboard": [[
                    {"text": "✅ Approve", "callback_data": f"approve:{job_id}"},
                    {"text": "❌ Reject", "callback_data": f"reject:{job_id}"}
                ]]
            }
        }
    )

