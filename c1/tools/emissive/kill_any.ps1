Get-Process -Name 'MotorTown*' -ErrorAction SilentlyContinue | ForEach-Object { "KILL " + $_.Id; Stop-Process -Id $_.Id -Force }
Start-Sleep -Seconds 6
if (Get-Process -Name 'MotorTown*' -ErrorAction SilentlyContinue) { "STILL_RUNNING" } else { "GAME_CLOSED" }
