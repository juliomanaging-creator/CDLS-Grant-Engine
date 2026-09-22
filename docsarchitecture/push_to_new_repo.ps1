# ==========================================================
# CDLS Automated Git Repository Migrator & Pusher
# ==========================================================

$GitHubUser = "juliomanaging-creator"
$RepoName = "CDLS-Grant-Engine"

Write-Host "=============================================" -ForegroundColor Cyan
Write-Host "   Target Repo: https://github.com/$GitHubUser/$RepoName" -ForegroundColor Cyan
Write-Host "=============================================" -ForegroundColor Cyan

# 1. Remove existing remote if present
Write-Host "[INFO] Clearing existing git remote origins..." -ForegroundColor Yellow
git remote remove origin 2>$null

# 2. Add the new remote repository link
Write-Host "[INFO] Linking to new GitHub repository..." -ForegroundColor Yellow
git remote add origin "https://github.com/$GitHubUser/$RepoName.git"

# 3. Ensure branch is set to main
git branch -M main

# 4. Push all files, workflows, and dossiers to the new repository
Write-Host "[INFO] Pushing files to GitHub..." -ForegroundColor Yellow
git push -u origin main

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "=============================================" -ForegroundColor Green
    Write-Host "   [SUCCESS] REPO MIGRATED  PUSHED CLEANLY! " -ForegroundColor Green
    Write-Host "=============================================" -ForegroundColor Green
    Write-Host "-> View your new repo at: https://github.com/$GitHubUser/$RepoName" -ForegroundColor Cyan
} else {
    Write-Host "[ERROR] Push failed. Please check your GitHub credentials or ensure the repository was created on GitHub first." -ForegroundColor Red
}