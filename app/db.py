from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

Base = declarative_base()

engine = None
SessionLocal = None


def init_db(database_url: str):
    global engine, SessionLocal

    engine = create_engine(
        database_url,
        echo=False,
        future=True
    )

    SessionLocal = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        future=True
    )

    return engine