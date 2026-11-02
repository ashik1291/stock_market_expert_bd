@echo off
title stock_market_expert_bd - Quantitative Engine - Daily Pipeline
cd /d "%~dp0"
echo ===============================================================================
echo        STOCK_MARKET_EXPERT_BD: QUANTITATIVE INTELLIGENCE & ADVISORY PIPELINE
echo ===============================================================================
echo.
python scripts\run_daily_pipeline.py %*
echo.
echo ===============================================================================
echo Pipeline execution finished. Press any key to close this window.
pause >nul
