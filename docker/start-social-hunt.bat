@echo off
REM Social-Hunt Windows Startup Script
REM This script starts the Social-Hunt Docker containers automatically

echo Starting Social-Hunt...
echo.

REM Get the directory where this script is located
cd /d "%~dp0"

REM Check if Docker is running
docker info >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Docker is not running!
    echo Please start Docker Desktop and try again.
    pause
    exit /b 1
)

echo Docker is running. Starting Social-Hunt containers...
echo.

REM Start the containers
docker compose up -d

if %errorlevel% equ 0 (
    echo.
    echo ========================================
    echo Social-Hunt started successfully!
    echo Access the application at:
    echo   http://localhost:8000
    echo ========================================
    echo.
    echo To view logs: docker compose logs -f social-hunt
    echo To stop: docker compose down
    echo.
) else (
    echo.
    echo ERROR: Failed to start Social-Hunt containers.
    echo Please check the error messages above.
    echo.
    pause
    exit /b 1
)

REM Uncomment the line below if you want the window to stay open
REM pause

exit /b 0
