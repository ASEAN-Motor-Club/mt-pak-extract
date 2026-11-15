$ErrorActionPreference='Continue'
$SID='S-1-5-21-3780104137-2907468895-2817211549-1001'
$steam='C:\Program Files (x86)\Steam\steam.exe'
$act = New-ScheduledTaskAction -Execute $steam -Argument '-applaunch 1369670'
$pr  = New-ScheduledTaskPrincipal -UserId $SID -LogonType Interactive
Register-ScheduledTask -TaskName 'AMCLaunchMT4' -Action $act -Principal $pr -Force | Out-Null
Start-ScheduledTask -TaskName 'AMCLaunchMT4'
for ($i=0; $i -lt 8; $i++) {
  Start-Sleep -Seconds 8
  $p = Get-Process -Name 'MotorTown*' -ErrorAction SilentlyContinue
  if ($p) { $p | ForEach-Object { "LAUNCHED after " + (8*($i+1)) + "s pid=" + $_.Id + " session=" + $_.SessionId }; break }
}
$p2 = Get-Process -Name 'MotorTown*' -ErrorAction SilentlyContinue
if (-not $p2) { "STILL_NOT_STARTED" }
Unregister-ScheduledTask -TaskName 'AMCLaunchMT4' -Confirm:$false
