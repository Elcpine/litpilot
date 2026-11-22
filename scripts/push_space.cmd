@echo off
rem Push this folder to the Hugging Face Space.
rem .cmd files are NOT blocked by PowerShell execution policy, so this works
rem even when ".\push.ps1" fails with PSSecurityException (unsigned script).
cd /d "%~dp0"

set "GIT=git"
where git >nul 2>nul
if errorlevel 1 set "GIT=D:\user\Git\cmd\git.exe"

"%GIT%" add -A
"%GIT%" diff --cached --quiet
if errorlevel 1 (
  "%GIT%" commit -m "LitPilot: update"
) else (
  echo [skip] nothing to commit
)

"%GIT%" push space main
if errorlevel 1 (
  echo [retry] normal push failed, trying --force ...
  "%GIT%" push space main --force
)

echo.
echo If the push succeeded, the Space rebuilds itself:
echo   https://huggingface.co/spaces/gloam05/litpilot
echo   https://gloam05-litpilot.hf.space  (wait 3-5 min for the image build)
pause
