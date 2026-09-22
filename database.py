import os
from sqlalchemy import create_engine, Column, Integer, String, Numeric, Boolean, DateTime, ForeignKey, func
from sqlalchemy.orm import declarative_base, sessionmaker, relationship

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/cdls_production")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class Grant(Base):
    __tablename__ = "grants"
    id = Column(Integer, primary_key=True, index=True)
    grant_name = Column(String, nullable=False)
    agency_source = Column(String, nullable=False)
    total_amount = Column(Numeric(12, 2), nullable=False)
    disbursed_amount = Column(Numeric(12, 2), default=0.00)
    status = Column(String, default="Active")
    created_at = Column(DateTime, server_default=func.now())
    milestones = relationship("Milestone", back_populates="grant", cascade="all, delete-orphan")

class Milestone(Base):
    __tablename__ = "milestones"
    id = Column(Integer, primary_key=True, index=True)
    grant_id = Column(Integer, ForeignKey("grants.id"), nullable=False)
    milestone_title = Column(String, nullable=False)
    allocated_funds = Column(Numeric(12, 2), nullable=False)
    is_completed = Column(Boolean, default=False)
    grant = relationship("Grant", back_populates="milestones")

def init_db():
    Base.metadata.create_all(bind=engine)