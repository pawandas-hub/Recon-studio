@echo off
cd /d "%~dp0\.."
echo [1/3] Removing corrupted Git index...
if exist ".git\index" del /f /q ".git\index"
if exist ".git\index.lock" del /f /q ".git\index.lock"
echo [2/3] Rebuilding Git index...
git reset
echo [3/3] Done! Git index has been completely restored.
pause
