# ==============================================================================
# stock_market_expert_bd — Windows Task Scheduler Automation Script
#
# Usage (in PowerShell):
#   .\scripts\setup_scheduled_tasks.ps1 -Action Install
#   .\scripts\setup_scheduled_tasks.ps1 -Action Show
#   .\scripts\setup_scheduled_tasks.ps1 -Action Uninstall
# ==============================================================================
param (
    [ValidateSet("Install", "Show", "Uninstall")]
    [string]$Action = "Show"
)

$RepoDir = Resolve-Path (Join-Path $PSScriptRoot "..")
$LogsDir = Join-Path $RepoDir "logs\cron"
if (-not (Test-Path $LogsDir)) {
    New-Item -ItemType Directory -Path $LogsDir -Force | Out-Null
}

# Resolve active Python interpreter
$PythonPath = ""
if (Test-Path "$RepoDir\.venv\Scripts\python.exe") {
    $PythonPath = "$RepoDir\.venv\Scripts\python.exe"
} elseif (Test-Path "$RepoDir\venv\Scripts\python.exe") {
    $PythonPath = "$RepoDir\venv\Scripts\python.exe"
} else {
    $PythonPath = (Get-Command python -ErrorAction SilentlyContinue).Source
    if (-not $PythonPath) {
        $PythonPath = "python.exe"
    }
}

$DailyTaskName = "DSE_Daily_Alpha_Cycle"
$WeeklyTaskName = "DSE_Weekly_Knowledge_Refresh"

$DailyScript = Join-Path $RepoDir "scripts\auto_daily_alpha_routine.py"
$WeeklyScript = Join-Path $RepoDir "scripts\analyzer.py"

Write-Host "================================================================================" -ForegroundColor Cyan
Write-Host "🕒 DSE Quantitative Engine — Windows Scheduled Tasks Manager" -ForegroundColor Cyan
Write-Host "   Repository Directory : $RepoDir"
Write-Host "   Python Interpreter   : $PythonPath"
Write-Host "   Log Directory        : $LogsDir"
Write-Host "================================================================================"

if ($Action -eq "Show") {
    Write-Host "`n[Tasks to Configure]:"
    Write-Host "1. $($DailyTaskName): Sunday-Thursday at 15:30"
    Write-Host "   Command: $PythonPath $DailyScript"
    Write-Host "2. $($WeeklyTaskName): Thursday at 18:00"
    Write-Host "   Command: $PythonPath $WeeklyScript category_a weekly"
    Write-Host "`nTo install these into Windows Task Scheduler, run:" -ForegroundColor Yellow
    Write-Host "   powershell -ExecutionPolicy Bypass -File .\scripts\setup_scheduled_tasks.ps1 -Action Install"
    
    Write-Host "`n[Current Status in Task Scheduler]:"
    Get-ScheduledTask -TaskName "DSE_*" -ErrorAction SilentlyContinue | Format-Table TaskName, State
}
elseif ($Action -eq "Install") {
    Write-Host "`n🔧 Installing Windows Scheduled Tasks..." -ForegroundColor Yellow

    # 1. Daily Alpha Task (Sun-Thu at 15:30)
    $DailyAction = New-ScheduledTaskAction -Execute $PythonPath -Argument "`"$DailyScript`"" -WorkingDirectory $RepoDir
    $DaysOfWeek = @("Sunday", "Monday", "Tuesday", "Wednesday", "Thursday")
    $DailyTrigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek $DaysOfWeek -At 3:30PM
    $Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable

    Register-ScheduledTask -TaskName $DailyTaskName -Action $DailyAction -Trigger $DailyTrigger -Settings $Settings -Description "DSE Daily Statistical Alpha & Pipeline Runner" -Force | Out-Null
    Write-Host "  ✅ Registered Task: $DailyTaskName (Sun-Thu at 15:30)" -ForegroundColor Green

    # 2. Weekly Knowledge Refresh Task (Thu at 18:00)
    $WeeklyAction = New-ScheduledTaskAction -Execute $PythonPath -Argument "`"$WeeklyScript`" category_a weekly" -WorkingDirectory $RepoDir
    $WeeklyTrigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek "Thursday" -At 6:00PM

    Register-ScheduledTask -TaskName $WeeklyTaskName -Action $WeeklyAction -Trigger $WeeklyTrigger -Settings $Settings -Description "DSE Weekly Knowledge Base Refresh" -Force | Out-Null
    Write-Host "  ✅ Registered Task: $WeeklyTaskName (Thursday at 18:00)" -ForegroundColor Green

    Write-Host "`n🎉 SUCCESS: All Windows Scheduled Tasks installed successfully!" -ForegroundColor Green
}
elseif ($Action -eq "Uninstall") {
    Write-Host "`n🗑️ Removing DSE Scheduled Tasks..." -ForegroundColor Yellow
    Unregister-ScheduledTask -TaskName $DailyTaskName -Confirm:$false -ErrorAction SilentlyContinue
    Unregister-ScheduledTask -TaskName $WeeklyTaskName -Confirm:$false -ErrorAction SilentlyContinue
    Write-Host "  ✅ Removed $DailyTaskName and $WeeklyTaskName" -ForegroundColor Green
}
