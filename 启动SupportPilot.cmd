@echo off
setlocal
title SupportPilot - Start

cd /d "%~dp0"

where docker >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Docker command was not found. Please install Docker Desktop.
    pause
    exit /b 1
)

docker version --format "{{.Server.Version}}" >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Docker Desktop is not running or Docker Engine is not ready.
    echo Start Docker Desktop, wait for Engine running, then run this script again.
    pause
    exit /b 1
)

echo Starting SupportPilot. Please wait...
docker compose up -d
if errorlevel 1 (
    echo.
    echo [ERROR] Failed to start SupportPilot. Current status:
    docker compose ps
    pause
    exit /b 1
)

set "FRONTEND_PORT="
for /f "tokens=2 delims=:" %%P in ('docker compose port frontend 80 2^>nul') do set "FRONTEND_PORT=%%P"
if not defined FRONTEND_PORT (
    echo.
    echo [ERROR] Could not determine the published frontend port.
    docker compose ps
    pause
    exit /b 1
)
set "FRONTEND_URL=http://localhost:%FRONTEND_PORT%"

set /a ATTEMPTS=0

:WAIT_FOR_APP
set /a ATTEMPTS+=1
powershell -NoLogo -NoProfile -Command "try { $api = Invoke-WebRequest -UseBasicParsing -Uri 'http://localhost:8000/ready' -TimeoutSec 3; $web = Invoke-WebRequest -UseBasicParsing -Uri '%FRONTEND_URL%' -TimeoutSec 3; if ($api.StatusCode -eq 200 -and $web.StatusCode -eq 200) { exit 0 } } catch {}; exit 1" >nul 2>&1
if not errorlevel 1 goto APP_READY

if %ATTEMPTS% GEQ 45 goto START_TIMEOUT
ping -n 3 127.0.0.1 >nul
goto WAIT_FOR_APP

:APP_READY
echo.
echo SupportPilot is ready. Opening the browser...
start "" "%FRONTEND_URL%"
ping -n 3 127.0.0.1 >nul
exit /b 0

:START_TIMEOUT
echo.
echo [ERROR] SupportPilot was not ready after 90 seconds. Current status:
docker compose ps
echo.
echo View logs with: docker compose logs --tail 100 api worker
pause
exit /b 1
