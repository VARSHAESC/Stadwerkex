@echo off
setlocal enabledelayedexpansion

echo ===================================================
echo   EnergyBot - Local OSRM Setup (Duesseldorf Region)
echo ===================================================
echo.
echo This script will download the regional OSM data and prepare the routing engine.
echo Requires Docker to be installed and running.
echo.

if not exist "osrm_data" (
    mkdir osrm_data
)

cd osrm_data

set FILE_NAME=duesseldorf-regbez-latest.osm.pbf
set FILE_URL=https://download.geofabrik.de/europe/germany/nordrhein-westfalen/!FILE_NAME!

if not exist "!FILE_NAME!" (
    echo [i] Downloading map data ~180MB...
    curl -L -o !FILE_NAME! !FILE_URL!
    if !ERRORLEVEL! neq 0 (
        echo [X] Download failed.
        pause
        exit /b
    )
    echo [v] Download complete.
) else (
    echo [i] Map data !FILE_NAME! already exists. Skipping download.
)

echo.
echo [i] Running OSRM Extract...
docker run --rm -v "%cd%:/data" osrm/osrm-backend osrm-extract -p /opt/car.lua /data/!FILE_NAME!

echo.
echo [i] Running OSRM Partition...
docker run --rm -v "%cd%:/data" osrm/osrm-backend osrm-partition /data/!FILE_NAME!

echo.
echo [i] Running OSRM Customize...
docker run --rm -v "%cd%:/data" osrm/osrm-backend osrm-customize /data/!FILE_NAME!

echo.
echo ===================================================
echo   OSRM Data Prep Complete!
echo   You can now start the app using run_energybot.bat
echo ===================================================
pause
