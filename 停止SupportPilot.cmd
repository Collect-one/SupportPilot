@echo off
setlocal
title SupportPilot - Stop

cd /d "%~dp0"

where docker >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Docker command was not found. Please install Docker Desktop.
    pause
    exit /b 1
)

docker version --format "{{.Server.Version}}" >nul 2>&1
if errorlevel 1 (
    echo Docker Desktop is not running. SupportPilot is already unavailable.
    ping -n 4 127.0.0.1 >nul
    exit /b 0
)

echo Stopping SupportPilot. Please wait...
docker compose stop
if errorlevel 1 (
    echo.
    echo [ERROR] Failed to stop SupportPilot. Current status:
    docker compose ps
    pause
    exit /b 1
)

echo.
echo SupportPilot has stopped. Database, knowledge base, and uploads are preserved.
ping -n 4 127.0.0.1 >nul
exit /b 0
