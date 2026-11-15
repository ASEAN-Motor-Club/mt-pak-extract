$ue='D:\UE_5.5\Engine\Binaries\Win64\UnrealEditor-Cmd.exe'
$log='D:\UEProjects\C1\Saved\Logs\cook_client.log'
$args=@('D:\UEProjects\C1\C1.uproject','-run=cook','-TargetPlatform=Windows','-CookAll','-unattended','-nop4','-nosplash','-stdout','-FullStdOutLogOutput')
$mi='D:\UEProjects\C1\Saved\Cooked\Windows\C1\Content\Mods\C1Full\Materials\MI_C1_mat_mat_window3_glass_sh'
foreach($e in 'uasset','uexp','ubulk'){ if(Test-Path "$mi.$e"){ Remove-Item "$mi.$e" -Force; Write-Output "DELETED_COOKED $e" } }
Write-Output ("CLIENT_COOK_START " + (Get-Date -Format 'HH:mm:ss'))
$p=Start-Process -FilePath $ue -ArgumentList $args -NoNewWindow -PassThru
$p.WaitForExit()
Write-Output ("CLIENT_COOK_RC " + $p.ExitCode)
$mi='D:\UEProjects\C1\Saved\Cooked\Windows\C1\Content\Mods\C1Full\Materials\MI_C1_mat_mat_window3_glass_sh.uasset'
if (Test-Path $mi) { Get-Item $mi | ForEach-Object { Write-Output ("CLIENT_MI " + $_.Length + " " + $_.LastWriteTime.ToString('HH:mm:ss')) } } else { Write-Output 'CLIENT_MI_MISSING' }
