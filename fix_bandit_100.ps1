# ==============================================================================
# CDLS Platform — Bandit Fix: Restore 100/100 by Fixing Real Findings
# Run #12 failed at 80/100 because Bandit found genuine HIGH-severity issues.
#
# IMPORTANT: The goal is to FIX the code, not suppress warnings.
#            # nosec annotations are a last resort for verified false positives only.
#
# Usage: .\fix_bandit_100.ps1
# ==============================================================================

[CmdletBinding()]
param([switch]$ScanOnly)

Write-Host "`n====================================================" -ForegroundColor Cyan
Write-Host "  CDLS — Bandit Fix: Restore 100/100 via Real Fixes" -ForegroundColor Cyan
Write-Host "  Addresses Run #12 failure (80/100 < 85/100 floor)" -ForegroundColor Cyan
Write-Host "====================================================`n" -ForegroundColor Cyan

# ------------------------------------------------------------------------------
# STEP 1: Install Bandit locally (WinError 2 fix)
# ------------------------------------------------------------------------------
Write-Host "[1/5] Installing Bandit in local environment..." -ForegroundColor Yellow
python -m pip install bandit pip-audit detect-secrets -q
Write-Host "  [OK] Bandit installed" -ForegroundColor Green

# ------------------------------------------------------------------------------
# STEP 2: Run Bandit to see exactly what it found (the real findings)
# ------------------------------------------------------------------------------
Write-Host "`n[2/5] Running Bandit scan — showing all findings..." -ForegroundColor Yellow
Write-Host "      (This reveals WHAT Run #12 found that dropped the score to 80/100)"
Write-Host ""

$banditOutput = python -m bandit -r . `
    --exclude "./.git,./venv,./.venv,./node_modules,./CDLS_Security_Audit_Evidence,./tests" `
    -f txt 2>&1

Write-Host $banditOutput
$banditOutput | Out-File "bandit_findings_raw.txt" -Encoding utf8

Write-Host "`n  [SAVED] Full findings in bandit_findings_raw.txt" -ForegroundColor Cyan

if ($ScanOnly) {
    Write-Host "`n  Scan-only mode. Review bandit_findings_raw.txt before running fixes." -ForegroundColor Yellow
    exit 0
}

# ------------------------------------------------------------------------------
# STEP 3: Fix Finding #1 (most likely) — B106 Hardcoded Password in database.py
#
# Bandit B106 triggers on: os.getenv("DATABASE_URL", "postgresql://postgres:postgres@...")
# The fix: Remove the fallback default. Raise ValueError if unset.
# We do NOT add # nosec — we fix the actual issue.
# ------------------------------------------------------------------------------
Write-Host "`n[3/5] Fixing B106 — Hardcoded password in database.py..." -ForegroundColor Yellow

$dbFile = "database.py"
if (Test-Path $dbFile) {
    $content = Get-Content $dbFile -Raw

    # Pattern 1: os.getenv with hardcoded postgres:postgres fallback
    $pattern1 = 'DATABASE_URL\s*=\s*os\.getenv\([^,]+,\s*["\']postgresql://postgres:postgres[^"\']*["\']\)'
    $fix1     = @'
# B106 fix: No hardcoded password fallback — raise ValueError if DATABASE_URL unset
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError(
        "DATABASE_URL environment variable must be set.\n"
        "Example: postgresql://cdls_app:<password>@localhost:5432/cdls_production\n"
        "Generate password: python -c \"import secrets; print(secrets.token_hex(24))\""
    )
'@

    # Pattern 2: simpler fallback form
    $pattern2 = 'DATABASE_URL\s*=\s*os\.getenv\("DATABASE_URL",\s*"postgresql://[^"]*postgres[^"]*"\)'

    if ($content -match $pattern1 -or $content -match $pattern2) {
        # Replace the entire DATABASE_URL assignment block
        $content = $content -replace $pattern1, $fix1
        $content = $content -replace $pattern2, $fix1
        Set-Content $dbFile $content -Encoding utf8
        Write-Host "  [FIXED] database.py: Removed hardcoded PostgreSQL credential fallback (B106)" -ForegroundColor Green
    } elseif ($content -match "postgres:postgres") {
        Write-Host "  [WARN] Found 'postgres:postgres' in database.py — review manually" -ForegroundColor Yellow
        Write-Host "         Pattern may differ from expected. Check bandit_findings_raw.txt for line number."
    } else {
        Write-Host "  [OK] No hardcoded postgres credential fallback found in database.py" -ForegroundColor Gray
    }
} else {
    Write-Host "  [SKIP] database.py not found" -ForegroundColor DarkGray
}

# ------------------------------------------------------------------------------
# STEP 4: Fix Finding #2 (likely) — B104 Binding to 0.0.0.0 in CMD
#
# Bandit B104 triggers on: uvicorn main:app --host 0.0.0.0
# in Dockerfile CMD or any Python code.
# Fix: Use 127.0.0.1 in Dockerfile CMD; nginx handles external traffic.
# Note: If intentional (Docker internal network), use # nosec B104 with justification.
# ------------------------------------------------------------------------------
Write-Host "`n[4/5] Fixing B104 — Binding to 0.0.0.0..." -ForegroundColor Yellow

foreach ($dfFile in @("Dockerfile", "Dockerfile.api", "Dockerfile.vdr")) {
    if (Test-Path $dfFile) {
        $dfContent = Get-Content $dfFile -Raw

        if ($dfContent -match '"--host",\s*"0\.0\.0\.0"') {
            # Change to 127.0.0.1 — nginx handles external traffic
            $dfContent = $dfContent -replace '"--host",\s*"0\.0\.0\.0"', '"--host", "127.0.0.1"'
            Set-Content $dfFile $dfContent -Encoding utf8
            Write-Host "  [FIXED] $dfFile: uvicorn --host changed to 127.0.0.1 (B104)" -ForegroundColor Green
        } elseif ($dfContent -match '--host\s+0\.0\.0\.0') {
            $dfContent = $dfContent -replace '--host\s+0\.0\.0\.0', '--host 127.0.0.1'
            Set-Content $dfFile $dfContent -Encoding utf8
            Write-Host "  [FIXED] $dfFile: uvicorn --host 0.0.0.0 → 127.0.0.1 (B104)" -ForegroundColor Green
        } elseif ($dfContent -match '"0\.0\.0\.0"') {
            Write-Host "  [WARN] $dfFile: Found 0.0.0.0 — review context before fixing" -ForegroundColor Yellow
            Write-Host "         If this is for Docker internal networking, add:"
            Write-Host '         # nosec B104  # Docker internal network: nginx proxies external traffic'
        } else {
            Write-Host "  [OK] $dfFile: No 0.0.0.0 binding found" -ForegroundColor Gray
        }
    }
}

# main.py uvicorn run call
if (Test-Path "main.py") {
    $mainContent = Get-Content "main.py" -Raw
    if ($mainContent -match 'host\s*=\s*"0\.0\.0\.0"') {
        $mainContent = $mainContent -replace 'host\s*=\s*"0\.0\.0\.0"', 'host = "127.0.0.1"'
        Set-Content "main.py" $mainContent -Encoding utf8
        Write-Host "  [FIXED] main.py: host changed from 0.0.0.0 to 127.0.0.1 (B104)" -ForegroundColor Green
    }
}

# ------------------------------------------------------------------------------
# STEP 5: Fix any remaining HIGH findings based on bandit output
# Check bandit_findings_raw.txt for other Severity: HIGH findings
# ------------------------------------------------------------------------------
Write-Host "`n[5/5] Checking for remaining HIGH/CRITICAL findings..." -ForegroundColor Yellow

$findings = Get-Content "bandit_findings_raw.txt" -ErrorAction SilentlyContinue
if ($findings) {
    $highCount    = ($findings | Select-String "Severity: High").Count
    $critCount    = ($findings | Select-String "Severity: Critical").Count
    $mediumCount  = ($findings | Select-String "Severity: Medium").Count

    Write-Host ""
    Write-Host "  Current Bandit finding counts (BEFORE fixes committed):"
    Write-Host "    Critical : $critCount" -ForegroundColor $(if ($critCount -gt 0) { "Red" } else { "Green" })
    Write-Host "    High     : $highCount" -ForegroundColor $(if ($highCount -gt 0) { "Red" } else { "Green" })
    Write-Host "    Medium   : $mediumCount" -ForegroundColor $(if ($mediumCount -gt 0) { "Yellow" } else { "Green" })

    if ($highCount -gt 0 -or $critCount -gt 0) {
        Write-Host ""
        Write-Host "  HIGH/CRITICAL FINDINGS THAT NEED FIXING:" -ForegroundColor Red
        $findings | Select-String -Context 3,1 "Severity: (High|Critical)" | ForEach-Object {
            Write-Host "  $_" -ForegroundColor Yellow
        }
        Write-Host ""
        Write-Host "  Fix each HIGH/CRITICAL by addressing the ROOT CAUSE." -ForegroundColor Red
        Write-Host "  Use # nosec ONLY for verified false positives — document why." -ForegroundColor Red
    } else {
        Write-Host "  [OK] No HIGH or CRITICAL findings remain" -ForegroundColor Green
    }
}

# Re-run sentinel to check score after fixes
Write-Host "`n  Running security_sentinel.py to check new score..." -ForegroundColor Cyan
python security_sentinel.py

Write-Host "`n====================================================" -ForegroundColor Cyan
Write-Host " SUMMARY" -ForegroundColor Cyan
Write-Host "====================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host " IMPORTANT: The CI failure was CORRECT behavior."
Write-Host " Bandit found real issues. The gate worked as designed."
Write-Host " Fix the code — don't silence Bandit."
Write-Host ""
Write-Host " Files written: bandit_findings_raw.txt"
Write-Host ""
Write-Host " After all HIGH findings are fixed:"
Write-Host "   git add ."
Write-Host '   git commit -m "fix: resolve Bandit HIGH findings (B106/B104) — restore 100/100"'
Write-Host "   git push origin main"
Write-Host "   # Watch Run #13 pass at 100/100"
Write-Host ""
Write-Host " RULE: 100/100 earned through real fixes, not # nosec suppression."
Write-Host "====================================================`n" -ForegroundColor Cyan
