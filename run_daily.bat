@echo off
title DSE Quantitative Intelligence Engine - Daily Pipeline
cd /d "%~dp0"
echo ===============================================================================
echo        DSE QUANTITATIVE ENGINE - AUTOMATED INSTITUTIONAL PIPELINE
echo ===============================================================================
echo.
python scripts\run_daily_pipeline.py %*
echo.
echo ===============================================================================
echo Pipeline execution finished. Press any key to close this window.
pause >nul
