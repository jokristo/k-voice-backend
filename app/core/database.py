from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from app.core.config import settings


def _is_sqlite(url: str) -> bool:
    return url.startswith("sqlite")


def _get_engine():
    url = settings.database_url
    connect_args: dict = {}
    engine_kwargs: dict = {}

    if _is_sqlite(url):
        connect_args["check_same_thread"] = False
    else:
        # PostgreSQL (prod Render) : connexions résilientes
        engine_kwargs["pool_pre_ping"] = True
        engine_kwargs["pool_size"] = 5
        engine_kwargs["max_overflow"] = 10

    return create_engine(url, connect_args=connect_args, **engine_kwargs)


engine = _get_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
