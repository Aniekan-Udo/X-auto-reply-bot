import os
import logging
from datetime import datetime, timezone
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request

load_dotenv()
logger = logging.getLogger(__name__)

app = FastAPI(title="Twitter Bot API", version="1.0.0")

AIRTABLE_API_KEY = os.getenv("AIRTABLE_API_KEY")
AIRTABLE_BASE_ID = os.getenv("AIRTABLE_BASE_ID")

def get_metrics_table():
    from pyairtable import Api
    return Api(AIRTABLE_API_KEY).table(AIRTABLE_BASE_ID, "Metrics")

def get_audit_table():
    from pyairtable import Api
    return Api(AIRTABLE_API_KEY).table(AIRTABLE_BASE_ID, "Audit Log")

@app.post("/telegram/callback")
async def telegram_callback(request: Request):
    try:
        update = await request.json()
        callback = update.get("callback_query")
        if not callback:
            return {"ok": True}
        action, job_id = callback["data"].split(":")
        approved = action == "approve"
        from safety_compliance.moderator import HITLModerator
        await HITLModerator.resume(job_id, approved)
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/metrics")
async def get_metrics():
    try:
        records = get_metrics_table().all()
        metrics = {r["fields"]["Metric"]: r["fields"].get("Count", 0) for r in records if "Metric" in r["fields"]}
        total = sum([metrics.get("replies_posted", 0), metrics.get("replies_dry_run", 0), metrics.get("replies_rejected", 0), metrics.get("replies_hitl", 0)])
        posted = metrics.get("replies_posted", 0) + metrics.get("replies_dry_run", 0)
        rate = round((posted / total * 100), 2) if total > 0 else 0
        return {"metrics": metrics, "total_processed": total, "success_rate": f"{rate}%", "retrieved_at": datetime.now(timezone.utc).isoformat()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/metrics/audit")
async def get_audit_log(limit: int = 50):
    try:
        records = get_audit_table().all(sort=["Timestamp"], max_records=limit)
        return {"count": len(records), "records": [r["fields"] for r in records]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health_check():
    return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}
8