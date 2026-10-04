# Supervisor loop for backend.trading_floor: if the engine process ever exits, for any
# reason (crash, an uncaught cancellation past Trader.run()'s except Exception, a sleep/
# resume issue, anything), this relaunches it after a short pause instead of leaving it
# silently dead until someone notices.

$ErrorActionPreference = "Stop"
$env:PYTHONUNBUFFERED = "1"

(& "C:\ProgramData\anaconda3\Scripts\conda.exe" "shell.powershell" "hook") | Out-String | Invoke-Expression
conda activate AIAgent
Set-Location "S:\AIProjects\StockTrader2026"

while ($true) {
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Add-Content -Path "trading_floor_supervisor.log" -Value "$timestamp - starting backend.trading_floor"
    $proc = Start-Process -FilePath "python" -ArgumentList "-u","-m","backend.trading_floor" `
        -RedirectStandardOutput "trading_floor.out.log" -RedirectStandardError "trading_floor.err.log" `
        -NoNewWindow -PassThru -Wait
    $exitCode = $proc.ExitCode
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Add-Content -Path "trading_floor_supervisor.log" -Value "$timestamp - backend.trading_floor exited (code $exitCode), restarting in 30s"
    Start-Sleep -Seconds 30
}
