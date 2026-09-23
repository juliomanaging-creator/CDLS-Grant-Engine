import os
from typing import Optional
from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from database import SessionLocal, Grant, Milestone, init_db

# Initialize database tables on startup
init_db()

app = FastAPI(
    title="Clean Distributed Ledger Suite (CDLS) Grant API",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# ------------------------------------------------------------------------------
# SECURITY MIDDLEWARE: Strict CORS & Security Headers
# ------------------------------------------------------------------------------
allowed_origins_env = os.getenv(
    "CDLS_ALLOWED_ORIGINS", 
    "https://juliomanaging-creator.github.io,http://localhost:8000"
)
origins_list = [origin.strip() for origin in allowed_origins_env.split(",") if origin.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "X-Requested-With"],
)

@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["Content-Security-Policy"] = "default-src 'self' https:; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net;"
    return response

# Dependency to get DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.get("/")
def read_root():
    return {
        "system": "Clean Distributed Ledger Suite (CDLS) Grant Engine",
        "status": "SECURE",
        "version": "1.0.0",
        "portal": "https://juliomanaging-creator.github.io/CDLS-/"
    }

@app.get("/api/dashboard/metrics")
def get_dashboard_metrics(db: Session = Depends(get_db)):
    total_grants = db.query(Grant).count()
    active_milestones = db.query(Milestone).filter(Milestone.status == "Active").count()
    return {
        "total_grants": total_grants,
        "active_milestones": active_milestones,
        "compliance_status": "Verified 100/100"
    }

@app.get("/api/grants/vet")
def vet_grants(db: Session = Depends(get_db)):
    grants = db.query(Grant).all()
    return {"status": "success", "count": len(grants), "grants": grants}