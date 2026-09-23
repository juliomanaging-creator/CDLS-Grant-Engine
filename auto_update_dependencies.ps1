Write-Host "=============================================" -ForegroundColor Cyan
Write-Host "   CDLS AUTOMATED DEPENDENCY PATCHING SCRIPT   " -ForegroundColor Cyan
Write-Host "=============================================" -ForegroundColor Cyan

$reqPath = "requirements.txt"
if (Test-Path $reqPath) {
    Write-Host "[INFO] Inspecting and patching requirements.txt..." -ForegroundColor Yellow
    $content = Get-Content$reqPath -Raw
    
    # Securely patch older chromadb versions to remediate CVE flags
    if ($content -match "chromadb") {
        $content =$content -replace "chromadb[>=<~]+[\d\.]+", "chromadb>=1.5.9"
    } else {
        $content += "`nchromadb>=1.5.9"
    }

    # Ensure huggingface-hub is securely pinned
    if ($content -match "huggingface-hub") {
        $content = $content -replace "huggingface-hub[>=<~]+[\d\.]+", "huggingface-hub>=1.31.0"
    } else {
        $content += "`nhuggingface-hub>=1.31.0"
    }
    
    Set-Content -Path $reqPath -Value$content -Encoding utf8
    Write-Host "[OK] requirements.txt patched with secure minimum versions." -ForegroundColor Green
} else {
    Write-Host "[WARN] requirements.txt not found!" -ForegroundColor Red
    exit 1
}

Write-Host "[INFO] Upgrading pip and installing packages..." -ForegroundColor Yellow
python -m pip install --upgrade pip
python -m pip install --upgrade -r requirements.txt

Write-Host "[INFO] Executing local Security Sentinel..." -ForegroundColor Yellow
python security_sentinel.py

Write-Host "=============================================" -ForegroundColor Cyan
Write-Host "[SUCCESS] Auto-update and validation pipeline completed!" -ForegroundColor Green
Write-Host "=============================================" -ForegroundColor Cyan