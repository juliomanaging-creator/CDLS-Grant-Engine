import os
import hashlib
import secrets
from fastapi import FastAPI, HTTPException, Security, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

vdr_app = FastAPI()
security = HTTPBearer()

VAULT_DIR = os.path.abspath("secure_vault")

def secure_path_resolution(filename: str) -> str:
    # Resolve absolute path and enforce vault confinement
    safe_path = os.path.realpath(os.path.join(VAULT_DIR, filename))
    if not safe_path.startswith(VAULT_DIR):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: Path traversal detected."
        )
    return safe_path

def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()

@vdr_app.get("/vdr/download/{filename}")
def download_vdr_document(filename: str, credentials: HTTPAuthorizationCredentials = Security(security)):
    target_path = secure_path_resolution(filename)
    if not os.path.exists(target_path):
        raise HTTPException(status_code=404, detail="Document not found.")
    
    return {"status": "SUCCESS", "filepath": target_path, "message": "Document retrieved securely."}