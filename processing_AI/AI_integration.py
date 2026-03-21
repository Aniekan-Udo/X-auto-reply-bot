from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from tenacity import retry, stop_after_attempt, wait_exponential

import asyncio
import logging

from limits import parse
from limits.storage import MemoryStorage
from limits.strategies import FixedWindowRateLimiter

import logging
import os  
from ingestion_layer.models import TweetEvent
from dotenv import load_dotenv

from celery import Celery
app = Celery('tasks', broker='redis://localhost:6379/0')

load_dotenv()

groq_api_key=os.getenv("GROQ_API_KEY")
logger = logging.getLogger(__name__)

# Setup
storage = MemoryStorage()
rate_limiter = FixedWindowRateLimiter(storage)
limit = parse("60 per hour")

llm = ChatGroq(model="llama-3.3-70b-versatile", groq_api_key=groq_api_key)


spam_signals = [
    # Get rich quick
    "100x", "1000x", "guaranteed profit", "guaranteed returns",
    "risk free", "risk-free", "no risk",
    # Signal services
    "signals", "dm for calls", "dm for signals", "paid signals",
    "free signals", "vip signals", "join our group",
    # Pump and dump
    "pump", "next 100x", "gem alert", "low cap gem",
    "before it pumps", "get in early",
    # Copy trading scams
    "copy my trades", "copy trading", "follow my trades",
    "i turned $100 into",
    # Insider/manipulation
    "insider tip", "insider info",
    "my source says",
    # Promo spam
    "click here", "bit.ly", "t.me/", "telegram",
    "subscribe now", "limited offer", "act fast",
    # Fake giveaways
    "giveaway", "airdrop", "free crypto", "free bitcoin",
    "double your",
]

prompt = ChatPromptTemplate.from_messages([
    ("system", """You are a sharp, witty trading analyst for [Brand]. 
You speak like an experienced trader who has seen it all — 
the pumps, the dumps, the euphoria, and the rekt portfolios.

Your tone is:
- Clever and slightly sarcastic, never mean
- Knowledgeable — reference real market concepts, history, and trader culture
- Educational but never preachy
- Peer-to-peer — talk to traders as equals, not customers
- Concise — maximum 280 characters unless the insight genuinely needs more

Rules:
- Never give direct buy or sell advice
- Never predict prices
- You can comment on market behaviour, patterns, and psychology freely
- If asked for direct financial advice, deflect with wit 
  e.g. "My crystal ball is in the shop — consult a financial advisor"
- Use trading slang naturally: rekt, moon, dump, whale, FOMO, DYOR etc.

Here are examples of how to respond:

Tweet: "This coin just pumped 50% on no news wtf"
Reply: "Classic meme coin chaos. Whale sneezed or an influencer hit post — same energy. What pumps for no reason tends to dump for even less. DYOR before chasing 🎢"

Tweet: "Should I buy BTC right now?"
Reply: "My trading license is in the mail What I can tell you — zoom out, check the weekly, and never trade more than you can afford to lose. DYOR always."

Tweet: "The market is crashing everything is over"
Reply: "Every cycle has a graveyard of 'this is the end' tweets. Zoom out — BTC has died 400+ times according to headlines. Volatility is the admission fee for the gains 📉📈"

Tweet: "Your platform keeps freezing during high volatility"
Reply: "That's on us — sorry! High traffic moments are exactly when you need us most. DM us your details and we'll prioritise this fix 🔧"

Tweet: "100x gem alert DM me for signals"
Reply: SKIP

Tweet: "guaranteed profit strategy follow me"
Reply: SKIP

If the tweet is spam, a signal service, pump promotion, or asks for direct 
financial advice with no room for wit — reply with exactly: SKIP
"""),
    ("user", "{input}")
])

chain = prompt | llm

@app.task(bind=True, max_retries=3)
def process_event(self, event_data: dict) -> str | None:
    from ingestion_layer.models import TweetEvent
    event = TweetEvent(**event_data)

    if not rate_limiter.hit(limit):
        logger.warning("rate limit exceeded — skipping tweet %s", event.tweet_id)
        return None

    trigger = next((s for s in spam_signals if s in event.text.lower()), None)
    if trigger:
        logger.info("pre-filter triggered '%s' — skipping tweet %s", trigger, event.tweet_id)
        return None

    try:
        # run async _call_llm in sync context
        reply = asyncio.run(_call_llm(event))
        from safety_compliance.moderator import moderate
        moderate.delay(event.tweet_id, reply)  # Send for human-in-the-loop moderation
        return None
    except Exception as exc:
        logger.error("error processing tweet %s", event.tweet_id, exc_info=True)
        raise self.retry(exc=exc, countdown=2 ** self.request.retries)
    
    
 

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
async def _call_llm(event: TweetEvent) -> str | None:
    try:
        response = await chain.ainvoke({"input": event.text})
        reply = response.content.strip()

        if reply == "SKIP":
            logger.info("Skipping irrelevant tweet = %s", event.tweet_id)
            return None
        logger.info("Hand-off to layer 4  reply=%s | tweet=%s", reply, event.tweet_id)

        return reply
    except Exception as e:
        logger.error("Error processing tweet %s: %s", event.tweet_id, str(e), exc_info=True)
        raise  # Reraise to trigger retry