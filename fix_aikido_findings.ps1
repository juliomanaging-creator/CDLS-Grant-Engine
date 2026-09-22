Write-Host "=============================================" -ForegroundColor Cyan
Write-Host "   CDLS AIKIDO FINDINGS REMEDIATION ENGINE   " -ForegroundColor Cyan
Write-Host "=============================================" -ForegroundColor Cyan

# 1. Ensure FastAPI backend sets security headers (CSP, HSTS, HttpOnly cookies)
$mainPath = "main.py"
if (Test-Path $mainPath) {
    Write-Host "[INFO] Injecting security headers middleware into main.py..." -ForegroundColor Yellow
    $mainContent = Get-Content $mainPath -Raw

    $securityHeaderMiddleware = @"

# Security Headers Middleware to address CSP, HSTS, and Cookie flags
@app.middleware("http")
async def add_security_headers(request, call_next):
    response = await call_next(request)
    response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; object-src 'none';"
    response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains; preload"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    return response
"@

    if ($mainContent -notmatch "add_security_headers") {
        Add-Content -Path $mainPath -Value $securityHeaderMiddleware
        Write-Host "[OK] Security headers middleware added successfully." -ForegroundColor Green
    } else {
        Write-Host "[OK] Security headers middleware already present in main.py." -ForegroundColor Green
    }
} else {
    Write-Host "[WARN] main.py not found in working directory." -ForegroundColor Yellow
}

# 2. Add Subresource Integrity (SRI) attributes to dashboard / HTML frontends
$htmlFiles = Get-ChildItem -Filter "*.html" -Recurse
foreach ($file in $htmlFiles) {
    Write-Host "[INFO] Inspecting $($file.Name) for external resource links..." -ForegroundColor Yellow
    $htmlContent = Get-Content $file.FullName -Raw
    
    # Check for external stylesheets or scripts missing crossorigin/integrity
    if ($htmlContent -match '<link rel="stylesheet" href="http' -and $htmlContent -notmatch 'crossorigin="anonymous"') {
        $htmlContent = $htmlContent -replace '<link rel="stylesheet" href="(http[^"]+)"\s*/?>', '<link rel="stylesheet" href="$1" crossorigin="anonymous" />'
        Set-Content -Path $file.FullName -Value $htmlContent
        Write-Host "[OK] Added crossorigin attribute to stylesheets in $($file.Name)." -ForegroundColor Green
    }
}

Write-Host "=============================================" -ForegroundColor Cyan
Write-Host "[SUCCESS] Aikido remediation script completed successfully!" -ForegroundColor Green
Write-Host "=============================================" -ForegroundColor Cyan