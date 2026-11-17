# stock_market_expert_bd — Universal Windows PowerShell Launcher
# Ensures UTF-8 output encoding for Bengali and financial symbols
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

$script = Join-Path $PSScriptRoot "main.py"
& python $script $args
