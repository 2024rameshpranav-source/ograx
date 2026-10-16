from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from app.config import settings

# SQLite needs connect_args={"check_same_thread": False}
connect_args = {"check_same_thread": False} if settings.DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(
    settings.DATABASE_URL,
    connect_args=connect_args,
    pool_pre_ping=True
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

from sqlalchemy import text

def init_db():
    from app.db import models  # noqa: F401
    Base.metadata.create_all(bind=engine)

    # Automatically add missing columns if upgrading an existing SQLite database
    if settings.DATABASE_URL.startswith("sqlite"):
        with engine.connect() as conn:
            try:
                res = conn.execute(text("PRAGMA table_info(reports)"))
                existing_cols = {row[1] for row in res.fetchall()}
                if existing_cols:
                    if "coordinate_source" not in existing_cols:
                        conn.execute(text("ALTER TABLE reports ADD COLUMN coordinate_source VARCHAR(32) DEFAULT 'area_centre'"))
                    if "accuracy_m" not in existing_cols:
                        conn.execute(text("ALTER TABLE reports ADD COLUMN accuracy_m FLOAT"))
                    if "photo_url" not in existing_cols:
                        conn.execute(text("ALTER TABLE reports ADD COLUMN photo_url VARCHAR(512)"))
                    conn.commit()
            except Exception:
                pass
