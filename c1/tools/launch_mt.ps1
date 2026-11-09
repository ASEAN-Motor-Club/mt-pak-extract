$ErrorActionPreference = 'Continue'
# Launch Motor Town in the INTERACTIVE desktop session.
#
# Why this shape: our SSH shell lives in session 0, so Win32_Process.Create starts the game where
# there is no desktop -- it exits within seconds with no crash event and no log. A scheduled task
# created with /IT runs in the logged-on user's session, which is where Steam and the GPU are.
# Proven with a file-writing probe before trusting it for the real thing.
$tn  = 'AMC_LaunchMT'
$cmd = 'D:\launch_mt.cmd'
$steam = 'C:\Program Files (x86)\Steam\steam.exe'

if (Get-Process -Name 'MotorTown-Win64-Shipping' -ErrorAction SilentlyContinue) {
  Write-Output 'ALREADY_RUNNING'
  Get-Process -Name 'MotorTown-Win64-Shipping' | ForEach-Object { "  pid=$($_.Id) session=$($_.SessionId)" }
  exit 0
}

$lines = @(
  '@echo off',
  ('start "" "' + $steam + '" -applaunch 1369670')
)
[IO.File]::WriteAllLines($cmd, $lines)

& schtasks.exe /create /tn $tn /tr $cmd /sc once /st 23:59 /it /f | Out-Null
& schtasks.exe /run /tn $tn | Out-Null

$deadline = (Get-Date).AddSeconds(120)
$p = $null
while ((Get-Date) -lt $deadline) {
  Start-Sleep -Seconds 5
  $p = Get-Process -Name 'MotorTown-Win64-Shipping' -ErrorAction SilentlyContinue | Select-Object -First 1
  if ($p) { break }
}
if (-not $p) { Write-Output 'LAUNCH_TIMEOUT_120S'; exit 4 }
Start-Sleep -Seconds 8
$p = Get-Process -Name 'MotorTown-Win64-Shipping' -ErrorAction SilentlyContinue | Select-Object -First 1
Write-Output ("LAUNCHED pid=" + $p.Id + " session=" + $p.SessionId + " ws=" + [math]::Round($p.WorkingSet64/1MB) + "MB title='" + $p.MainWindowTitle + "'")
Write-Output ("autoload_marker=" + (Test-Path 'D:\c1_autoload.txt'))
Write-Output 'done'
