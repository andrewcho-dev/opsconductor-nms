import os
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://opsconductor:opsconductor@postgres:5432/opsconductor"
)

engine = create_engine(
    DATABASE_URL,
    echo=os.getenv("SQL_DEBUG", "false").lower() == "true"
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    """Dependency for FastAPI to inject database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Initialize database tables."""
    from .models import Base
    Base.metadata.create_all(bind=engine)
    _ensure_cli_credentials_column()


def _ensure_cli_credentials_column():
    """Ensure discovery_runs has cli_default_credentials column for older DBs."""
    inspector = inspect(engine)
    if "discovery_runs" not in inspector.get_table_names():
        return

    columns = {col["name"] for col in inspector.get_columns("discovery_runs")}
    if "cli_default_credentials" in columns:
        return

    with engine.begin() as connection:
        connection.execute(
            text(
                "ALTER TABLE discovery_runs "
                "ADD COLUMN cli_default_credentials JSONB NOT NULL DEFAULT '[]'::jsonb"
            )
        )
