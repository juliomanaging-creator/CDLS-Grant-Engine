# ==========================================================
# CDLS Workspace Structure & Linter Alignment Fixer
# ==========================================================

Write-Host "============================================-" -ForegroundColor Cyan
Write-Host "   Aligning Workspace Files & Pylance Path   " -ForegroundColor Cyan
Write-Host "============================================-" -ForegroundColor Cyan

# 1. Ensure .vscode directory exists and configure settings.json for workspace path indexing
New-Item -ItemType Directory -Force -Path ".vscode" | Out-Null
@"
{
    "python.analysis.extraPaths": ["."]
}
"@ | Set-Content -Encoding utf8 ".vscode\settings.json"
Write-Host "[OK] Configured .vscode\settings.json workspace path overrides." -ForegroundColor Green

# 2. Locate and relocate database.py to root if nested
$FoundDb = Get-ChildItem -Recurse -Filter "database.py" | Select-Object -First 1
$RootPath = Get-Location

if ($FoundDb) {
    if ($FoundDb.DirectoryName -ne $RootPath.Path) {
        Write-Host "[INFO] Moving database.py from $($FoundDb.DirectoryName) to project root..." -ForegroundColor Yellow
        Move-Item -Path $FoundDb.FullName -Destination "$RootPath\database.py" -Force
        Write-Host "[SUCCESS] database.py successfully placed in root directory." -ForegroundColor Green
    } else {
        Write-Host "[OK] database.py is already correctly placed in the root directory." -ForegroundColor Green
    }
} else {
    Write-Host "[WARN] database.py not found. Generating default clean database module..." -ForegroundColor Yellow
    @"
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
"@ | Set-Content -Encoding utf8 "database.py"
    Write-Host "[SUCCESS] Generated fresh database.py in root." -ForegroundColor Green
}

Write-Host ""
Write-Host "============================================-" -ForegroundColor Green
Write-Host " Workspace alignment complete! Please restart VS Code language server." -ForegroundColor Green
Write-Host "============================================-" -ForegroundColor Green