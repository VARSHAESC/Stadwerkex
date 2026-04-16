@echo off
setlocal enabledelayedexpansion

echo ===================================================
echo   EnergyBot - Infrastructure Platform Launcher
echo ===================================================
echo.

:: 1. Check for Docker
where docker >nul 2>&1
if %ERRORLEVEL% equ 0 (
    echo [✓] Docker detected. Starting via Docker Compose...
    docker compose up -d
    if !ERRORLEVEL! equ 0 (
        echo.
        echo Application is starting! 
        echo Access it at: http://localhost:9501
        pause
        exit /b
    )
    echo [WARN] Docker found but failed to start. Falling back to Python...
) else (
    echo [i] Docker not found. Looking for Python...
)

:: 2. Check for Python
where python >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [X] ERROR: Neither Docker nor Python was found on your system.
    echo Please install Python ^(3.10+^) or Docker to run this application.
    pause
    exit /b
)

:: 3. Setup Virtual Environment
if not exist "venv" (
    echo.
    echo [i] First-time setup: Creating a virtual environment...
    python -m venv venv
    if %ERRORLEVEL% neq 0 (
        echo [X] Failed to create virtual environment.
        pause
        exit /b
    )
    
    echo [i] Installing required libraries ^(this may take a few minutes^)...
    .\venv\Scripts\python -m pip install --upgrade pip
    .\venv\Scripts\python -m pip install -r requirements.txt
    if %ERRORLEVEL% neq 0 (
        echo [X] Failed to install libraries. Please check your internet connection.
        pause
        exit /b
    )
)

:: 4. Run App
echo.
echo [✓] Starting EnergyBot via Python...
echo Access it at: http://localhost:9501
.\venv\Scripts\streamlit run app.py --server.port=9501
if %ERRORLEVEL% neq 0 (
    echo.
    echo [WARN] Application stopped or failed to start.
    pause
)

exit /b