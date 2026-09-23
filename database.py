"""
CDLS Grant Engine — database.py
PostgreSQL persistence layer via SQLAlchemy ORM.

Security notes:
  - DATABASE_URL must be set via environment variable — no hardcoded fallback
  - B106 fix: removed postgresql://postgres:postgres default (Bandit HIGH finding)
  - B106 fix: ValueError raised at startup if DATABASE_URL not set
"""

import os
from sqlalchemy import (
    create_engine, Column, Integer, String,
    Numeric, Boolean, DateTime, ForeignKey, func
)
from sqlalchemy.orm import declarative_base, sessionmaker, relationship

# ---------------------------------------------------------------------------
# DATABASE_URL — required environment variable, no default
# B106 fix: no hardcoded credential fallback.
# Set in .env: DATABASE_URL=postgresql://cdls_app:<password>@localhost:5432/cdls_production
# Generate password: python -c "import secrets; print(secrets.token_hex(24))"
# ---------------------------------------------------------------------------
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError(
        "DATABASE_URL environment variable is required and not set.\n"
        "Set it in .env: DATABASE_URL=postgresql://cdls_app:<password>@localhost:5432/cdls_production\n"
        "For local dev, also start PostgreSQL: docker run -e POSTGRES_PASSWORD=<pw> -p 127.0.0.1:5432:5432 postgres:15-alpine"
    )

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class Grant(Base):
    """Institutional grant record with milestone tracking."""
    __tablename__ = "grants"

    id               = Column(Integer, primary_key=True, index=True)
    grant_name       = Column(String, nullable=False)
    agency_source    = Column(String, nullable=False)
    total_amount     = Column(Numeric(12, 2), nullable=False)
    disbursed_amount = Column(Numeric(12, 2), default=0.00)
    status           = Column(String, default="Active")
    created_at       = Column(DateTime, server_default=func.now())

    milestones = relationship(
        "Milestone",
        back_populates="grant",
        cascade="all, delete-orphan"
    )


class Milestone(Base):
    """Funding milestone linked to a parent Grant."""
    __tablename__ = "milestones"

    id               = Column(Integer, primary_key=True, index=True)
    grant_id         = Column(Integer, ForeignKey("grants.id"), nullable=False)
    milestone_title  = Column(String, nullable=False)
    allocated_funds  = Column(Numeric(12, 2), nullable=False)
    is_completed     = Column(Boolean, default=False)

    grant = relationship("Grant", back_populates="milestones")


def init_db() -> None:
    """Create all tables. Called at application startup."""
    Base.metadata.create_all(bind=engine)
