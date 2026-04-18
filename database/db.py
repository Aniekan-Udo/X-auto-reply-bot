from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from sqlalchemy import (create_engine, MetaData, Table, Column, Integer, 
                        String, Float, DateTime, func, ForeignKey)

from sqlalchemy.orm import Mapped, mapped_column, sessionmaker
from datetime import datetime
import logging
import os
from dotenv import load_dotenv


logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

load_dotenv()

DB_PASSWORD=os.getenv("DB_PASSWORD")
if not DB_PASSWORD:
    raise ValueError("DB_PASSWORD environment variable is not set. Please set it in your .env file.")


sql_url = f"postgresql://postgres:{DB_PASSWORD}@localhost:5432/twitter_auto_reply"


engine = create_engine(sql_url)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

class Model(DeclarativeBase):
    metadata = MetaData(naming_convention={
        "ix": "ix_%(column_0_label)s",
        "uq": "uq_%(table_name)s_%(column_0_name)s",
        "ck": "ck_%(table_name)s_%(constraint_name)s",
        "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
        "pk": "pk_%(table_name)s",
    })


class TwitterJob(Model):
    __tablename__ = "twitter_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    tweet_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    reply: Mapped[str] = mapped_column(String, nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)

def init_db():
    Model.metadata.create_all(engine)

#This interacts with the table
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()



class AccessDB:
    """Placeholder class for database access. In a real implementation, this would interface with an actual database."""
    @staticmethod
    def save_to_db(tweet_id, reply, score):
        db = SessionLocal()
        try:
            job = TwitterJob(tweet_id=tweet_id, reply=reply, score=score)
            db.add(job)
            db.commit()
            db.refresh(job)  # populates job.id after insert
            return job.id
        except Exception as e:
            db.rollback()
            logger.error("Failed to save job to database: %s", e, exc_info=True)
            raise
        finally:
            db.close()

    @staticmethod
    def load_from_db(job_id):
        db = SessionLocal()
        try:
            job = db.get(TwitterJob, job_id)
            if job is None:
                return None
            return {
                "tweet_id": job.tweet_id,
                "reply":    job.reply,
                "score":    job.score,
            }
        except Exception as e:
            logger.error("Failed to load job from database: %s", e, exc_info=True)
            raise
        finally:
            db.close()

