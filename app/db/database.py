import os
from time import perf_counter
from sqlalchemy import create_engine
from sqlalchemy import event
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "")
DB_POOL_SIZE = max(1, int(os.getenv("DB_POOL_SIZE", "5")))
DB_MAX_OVERFLOW = max(0, int(os.getenv("DB_MAX_OVERFLOW", "5")))
DB_POOL_TIMEOUT = max(1, int(os.getenv("DB_POOL_TIMEOUT_SECONDS", "30")))
DB_POOL_RECYCLE = max(60, int(os.getenv("DB_POOL_RECYCLE_SECONDS", "1800")))

_engine_options = {"pool_pre_ping": True}
if not DATABASE_URL.startswith("sqlite"):
    _engine_options.update({
        "pool_size": DB_POOL_SIZE,
        "max_overflow": DB_MAX_OVERFLOW,
        "pool_timeout": DB_POOL_TIMEOUT,
        "pool_recycle": DB_POOL_RECYCLE,
    })

engine = create_engine(DATABASE_URL, **_engine_options)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@event.listens_for(engine, "before_cursor_execute")
def _before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    _ = conn, cursor, statement, parameters, executemany
    context._guayabita_query_started = perf_counter()


@event.listens_for(engine, "after_cursor_execute")
def _after_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    _ = conn, cursor, statement, parameters, executemany
    from app.observability.metrics import metrics

    started = getattr(context, "_guayabita_query_started", None)
    if started is not None:
        metrics.observe("guayabita_sql_query_seconds", perf_counter() - started)
    metrics.increment("guayabita_sql_queries")


@event.listens_for(engine.pool, "checkout")
def _pool_checkout(dbapi_connection, connection_record, connection_proxy):
    _ = dbapi_connection, connection_record, connection_proxy
    from app.observability.metrics import metrics

    metrics.increment("guayabita_sql_pool_checkouts")


@event.listens_for(engine.pool, "checkin")
def _pool_checkin(dbapi_connection, connection_record):
    _ = dbapi_connection, connection_record
    from app.observability.metrics import metrics

    metrics.increment("guayabita_sql_pool_checkins")


class Base(DeclarativeBase):
    pass


def get_db():
    """Dependency para obtener sesión de base de datos."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
