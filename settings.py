import os
from pathlib import Path
from typing import List
# Editor configuration: python.analysis.extraPaths = ["."]

# Base directory definition
BASE_DIR = Path(__file__).resolve().parent

# --- Secure Secret Key Enforcement ---
# Eliminates public GitHub fallback vulnerability to prevent JWT forgery.
SECRET_KEY = os.getenv("SECRET_KEY")

if not SECRET_KEY:
    raise ValueError(
        "[CRITICAL SECURITY ERROR] SECRET_KEY environment variable is not set! "
        "Default fallbacks are strictly prohibited in production environments."
    )

# --- Application Configuration ---
DEBUG = os.getenv("DEBUG", "False").lower() in ("true", "1", "t", "yes")
ENVIRONMENT = os.getenv("ENVIRONMENT", "production")

# Database Configuration with secure fallback defaults
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_NAME = os.getenv("DB_NAME", "cdls_production")
DB_USER = os.getenv("DB_USER")
DB_PASS = os.getenv("DB_PASS")

if not DB_USER or not DB_PASS:
    raise ValueError(
        "[CRITICAL SECURITY ERROR] Database credentials (DB_USER/DB_PASS) must be explicitly provided via environment variables."
    )

DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# CORS Origins (Restricted to authorized institutional endpoints)
ALLOWED_ORIGINS: List[str] = [
    "https://trusted-gov.ca.gov",
    "https://salsa-portal.org",
    "https://cdls-ledger.internal"
]

if DEBUG:
    ALLOWED_ORIGINS.append("http://localhost:3000")
    ALLOWED_ORIGINS.append("http://127.0.0.1:3000")

# Security headers configuration flags
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SECURE = True
SESSION_COOKIE_SAMESITE = "lax"

print(f"[INIT] Settings loaded successfully for environment: {ENVIRONMENT.upper()}")