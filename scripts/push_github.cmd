@echo off
rem Mirror this folder to a GitHub / GitLab / Codeberg repository.
rem
rem Why this exists: Render's "Public Git Repository" only accepts
rem github.com / gitlab.com / bitbucket.org hosts. The HF Space repo
rem (https://huggingface.co/spaces/gloam05/litpilot.git) is a perfectly valid
rem git remote but Render rejects the URL, so we need a mirror on a host it knows.
rem
rem Usage:
rem   push_github.cmd https://github.com/USER/litpilot.git
rem   push_github.cmd https://gitlab.com/USER/litpilot.git
rem
rem HTTPS push asks for username + password; the password must be a personal
rem access token (GitHub: Settings -> Developer settings -> Tokens (classic),
rem scope "repo"; GitLab: Preferences -> Access Tokens, scope "write_repository").
cd /d "%~dp0"

if "%~1"=="" (
  echo Usage: push_github.cmd ^<repo-url^>
  echo   e.g. push_github.cmd https://github.com/gloam05/litpilot.git
  pause
  exit /b 1
)

set "GIT=git"
where git >nul 2>nul
if errorlevel 1 set "GIT=D:\user\Git\cmd\git.exe"

"%GIT%" add -A
"%GIT%" diff --cached --quiet
if errorlevel 1 (
  "%GIT%" commit -m "LitPilot: deploy snapshot"
) else (
  echo [skip] nothing new to commit
)

"%GIT%" remote remove gh 2>nul
"%GIT%" remote add gh "%~1"
"%GIT%" push gh main --force
if errorlevel 1 (
  echo [retry] pushing HEAD:main ...
  "%GIT%" push gh HEAD:main --force
)

echo.
if errorlevel 1 (
  echo Push FAILED. Common causes:
  echo   - password field must be a personal access token, not your account password
  echo   - token needs "repo" scope ^(GitHub^) / "write_repository" ^(GitLab^)
  echo   - repo does not exist yet: create an EMPTY public repo first
) else (
  echo Push OK. Now in Render pick "Public Git Repository" and paste %~1
)
pause
